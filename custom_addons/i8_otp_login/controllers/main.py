# -*- coding: utf-8 -*-
"""Log in with a code emailed to the account's address.

Hardened 2026-11-26. The shipped version stored the code in the requester's session and
never checked its expiry or the number of guesses, logged every code in clear, accepted any
account (administrators included, skipping their two-factor authentication) and created an
account for any address. Anyone could request a code for an administrator's email and guess
it.

Codes now come from the one-time-code engine (auth_otp), like every other code on the site:
one hashed code, 10 minutes, 5 tries, resend cooldown and hourly caps per address. On top,
this controller keeps the login-specific rules:

- only customer (portal) accounts log in this way; staff keep their password and 2FA;
- the answers are the same whether or not the address has an account;
- the login goes through Odoo's own authentication (`session.authenticate`), so login
  throttling and two-factor authentication apply;
- new accounts are created only where the website allows sign-ups;
- the redirect stays on this site.
"""
import logging
import re
import secrets
import time

from odoo import _, http
from odoo.exceptions import AccessDenied
from odoo.http import request

from odoo.addons.auth_otp.models.auth_otp import MAX_ATTEMPTS
from odoo.addons.web.controllers.utils import _get_login_redirect_url, ensure_db

_logger = logging.getLogger(__name__)

EMAIL_RE = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')
PURPOSE = 'email_login'
RESEND_COOLDOWN = 60         # seconds between codes for one visitor, whatever the address
SESSION_KEY = 'otp_login'
PROOF_KEY = 'otp_login_proof'
CREDENTIAL_TYPE = 'i8_email_otp'


def _local_url(url, default='/'):
    return url if url and url.startswith('/') and not url.startswith('//') and '\\' not in url else default


class SGGMOTPController(http.Controller):

    # Helpers
    # ------------------------------------------------------------------

    def _otp_user(self, email):
        """The active account whose login is `email`, if any (any kind)."""
        return request.env['res.users'].sudo().search([('login', 'in', list({email, email.lower()}))], limit=1)

    def _otp_signup_allowed(self):
        Users = request.env['res.users'].sudo()
        return hasattr(Users, '_get_signup_invitation_scope') and Users._get_signup_invitation_scope() == 'b2c'

    def _otp_can_log_in(self, user):
        """Customers, or a new customer where sign-up is open; never staff."""
        return (user and user.share) or (not user and self._otp_signup_allowed())

    def _otp_email_sender(self, email):
        def send(otp, code, token):
            template = request.env.ref('i8_otp_login.otp_email_template_otp_login')
            template.sudo().with_context(otp_code=code, email_to=email).send_mail(
                request.env.company.partner_id.id,
                force_send=True,
                email_values={'email_from': request.env.company.email_formatted, 'email_to': email},
            )
        return send

    # Routes
    # ------------------------------------------------------------------

    @http.route('/otp-login/send', type='jsonrpc', auth='public', website=True)
    def send_otp(self, email=None, **kw):
        ensure_db()
        email = (email or '').strip()
        if not EMAIL_RE.match(email):
            return {'status': 'error', 'message': _('Please enter a valid email address.')}

        previous = request.session.get(SESSION_KEY) or {}
        if previous.get('sent_at') and time.time() - previous['sent_at'] < RESEND_COOLDOWN:
            return {'status': 'error', 'message': _('Please wait a minute before asking for a new code.')}

        user = self._otp_user(email)
        # Codes go only to customer accounts, or to new customers where sign-up is open.
        # Anyone else gets the same answer, so the page can't tell who has an account.
        if self._otp_can_log_in(user):
            result = request.env['auth.otp']._otp_issue(
                PURPOSE, email=email, company=request.env.company, email_sender=self._otp_email_sender(email),
            )
            if result['error']:
                return {'status': 'error', 'message': result['error']}
        request.session[SESSION_KEY] = {'email': email, 'sent_at': time.time(), 'decoy_attempts': 0}
        return {'status': 'success'}

    @http.route(['/otp-login/verify', '/donation/verify_otp'], type='jsonrpc', auth='public', website=True)
    def verify_otp(self, code=None, redirect=None, **kw):
        ensure_db()
        # A copy: the session is only saved when a value changes.
        data = dict(request.session.get(SESSION_KEY) or {})
        if not data.get('email'):
            return {'status': 'error', 'message': _('Invalid OTP code.')}
        email = data['email']
        user = self._otp_user(email)

        if not self._otp_can_log_in(user):
            # No code was sent: answer exactly as for a wrong code, tries included.
            data['decoy_attempts'] = data.get('decoy_attempts', 0) + 1
            left = MAX_ATTEMPTS - data['decoy_attempts']
            if left <= 0:
                request.session.pop(SESSION_KEY, None)
                return {'status': 'error', 'message': _(
                    "That code is not right, and it cannot be used any more. Ask for a new one.")}
            request.session[SESSION_KEY] = data
            return {'status': 'error', 'message': _("That code is not right. %(left)s tries left.", left=left)}

        otp, error = request.env['auth.otp']._otp_verify(PURPOSE, code, email=email)
        if not otp:
            return {'status': 'error', 'message': error}
        request.session.pop(SESSION_KEY, None)

        if not user:
            user = request.env['res.users'].sudo().with_context(no_reset_password=True).create({
                'name': email.split('@')[0],
                'login': email,
                'email': email,
                'group_ids': [(6, 0, [request.env.ref('base.group_portal').id])],
            })

        # Log in through Odoo itself (throttling, 2FA). The proof only lives in this
        # visitor's server-side session, for a minute.
        proof = secrets.token_urlsafe(24)
        request.session[PROOF_KEY] = {'uid': user.id, 'proof': proof, 'until': time.time() + 60}
        try:
            auth_info = request.session.authenticate(request.env, {
                'type': CREDENTIAL_TYPE, 'login': user.login, 'proof': proof,
            })
        except AccessDenied:
            return {'status': 'error', 'message': _('Invalid OTP code.')}
        finally:
            request.session.pop(PROOF_KEY, None)

        final_url = _get_login_redirect_url(auth_info['uid'], _local_url(redirect))
        if '/web/login' in final_url and '/web/login/totp' not in final_url:
            final_url = '/'
        return {'status': 'success', 'redirect': final_url}
