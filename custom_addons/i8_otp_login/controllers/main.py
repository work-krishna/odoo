# -*- coding: utf-8 -*-
"""Log in with a code emailed to the account's address.

Hardened 2026-11-26. The shipped version stored the code in the requester's session and
never checked its expiry or the number of guesses, logged every code in clear, accepted any
account (administrators included, skipping their two-factor authentication) and created an
account for any address. Anyone could request a code for an administrator's email and guess
it. Now:

- only customer (portal) accounts log in this way; staff keep their password and 2FA;
- a code lasts 10 minutes and dies after 5 wrong tries; only a keyed hash is kept;
- one code a minute per visitor, 5 an hour per address (no email bombing);
- the answer is the same whether or not the address has an account;
- the login goes through Odoo's own authentication (`session.authenticate`), so login
  throttling and two-factor authentication apply;
- new accounts are created only where the website allows sign-ups;
- the redirect stays on this site, and codes never reach the logs.
"""
import logging
import re
import secrets
import time
from collections import defaultdict

from odoo import _, http
from odoo.exceptions import AccessDenied
from odoo.http import request
from odoo.tools import consteq
from odoo.tools.misc import hmac

from odoo.addons.web.controllers.utils import _get_login_redirect_url, ensure_db

_logger = logging.getLogger(__name__)

EMAIL_RE = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')
CODE_VALIDITY = 10 * 60      # seconds; the email says 10 minutes
RESEND_COOLDOWN = 60         # seconds between codes for one visitor
MAX_ATTEMPTS = 5             # wrong codes before a code dies
MAX_SENDS_PER_EMAIL_HOUR = 5
SESSION_KEY = 'otp_login'
PROOF_KEY = 'otp_login_proof'
CREDENTIAL_TYPE = 'i8_email_otp'

# (database, address) -> times codes were sent. In memory: production runs a single
# Odoo process; each extra worker would allow its own 5 an hour.
_sends = defaultdict(list)


def _new_code():
    return f"{secrets.randbelow(10 ** 6):06d}"


def _local_url(url, default='/'):
    return url if url and url.startswith('/') and not url.startswith('//') and '\\' not in url else default


class SGGMOTPController(http.Controller):

    # Helpers
    # ------------------------------------------------------------------

    def _otp_hash(self, email, salt, code):
        return hmac(request.env(su=True), 'i8_otp_login', f'{email}:{salt}:{code}')

    def _otp_user(self, email):
        """The active account whose login is `email`, if any (any kind)."""
        return request.env['res.users'].sudo().search([('login', 'in', list({email, email.lower()}))], limit=1)

    def _otp_signup_allowed(self):
        Users = request.env['res.users'].sudo()
        return hasattr(Users, '_get_signup_invitation_scope') and Users._get_signup_invitation_scope() == 'b2c'

    def _otp_throttled(self, email):
        key = (request.db, email.lower())
        now = time.time()
        _sends[key] = [sent for sent in _sends[key] if now - sent < 3600]
        return len(_sends[key]) >= MAX_SENDS_PER_EMAIL_HOUR

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
        if self._otp_throttled(email):
            return {'status': 'error', 'message': _('Too many codes were sent to this address. Please try again later.')}

        user = self._otp_user(email)
        # Codes go only to customer accounts, or to new customers where sign-up is open.
        # Anyone else gets the same answer, so the page can't tell who has an account.
        can_log_in = (user and user.share) or (not user and self._otp_signup_allowed())
        session_data = {'email': email, 'sent_at': time.time(), 'attempts': 0, 'hash': False}
        if can_log_in:
            code, salt = _new_code(), secrets.token_hex(8)
            session_data.update(hash=self._otp_hash(email, salt, code), salt=salt,
                                expires_at=time.time() + CODE_VALIDITY)
            _sends[(request.db, email.lower())].append(time.time())
            template = request.env.ref('i8_otp_login.otp_email_template_otp_login', raise_if_not_found=False)
            try:
                if template:
                    template.sudo().with_context(otp_code=code, email_to=email).send_mail(
                        request.env.company.partner_id.id,
                        force_send=True,
                        email_values={'email_from': request.env.company.email_formatted, 'email_to': email},
                    )
            except Exception:
                _logger.exception("Could not email a login code")
                return {'status': 'error', 'message': _('We could not send the code. Please try again later.')}
        request.session[SESSION_KEY] = session_data
        return {'status': 'success'}

    @http.route(['/otp-login/verify', '/donation/verify_otp'], type='jsonrpc', auth='public', website=True)
    def verify_otp(self, code=None, redirect=None, **kw):
        ensure_db()
        # A copy: the session is only saved when a value changes, so editing the stored dict
        # in place would never persist the attempt count.
        data = dict(request.session.get(SESSION_KEY) or {})
        wrong = {'status': 'error', 'message': _('Invalid OTP code.')}
        if not data or not data.get('hash'):
            return wrong
        if time.time() > data.get('expires_at', 0):
            request.session.pop(SESSION_KEY, None)
            return {'status': 'error', 'message': _('This code has expired. Please ask for a new one.')}
        code = re.sub(r'\s', '', code or '')
        if not consteq(data['hash'], self._otp_hash(data['email'], data['salt'], code)):
            data['attempts'] = data.get('attempts', 0) + 1
            left = MAX_ATTEMPTS - data['attempts']
            if left <= 0:
                request.session.pop(SESSION_KEY, None)
                return {'status': 'error', 'message': _('Too many wrong codes. Please ask for a new one.')}
            request.session[SESSION_KEY] = data
            return {'status': 'error', 'message': _('Invalid OTP code. %(left)s tries left.', left=left)}
        request.session.pop(SESSION_KEY, None)

        email = data['email']
        user = self._otp_user(email)
        if user and not user.share:
            return wrong
        if not user:
            if not self._otp_signup_allowed():
                return wrong
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
            return wrong
        finally:
            request.session.pop(PROOF_KEY, None)

        final_url = _get_login_redirect_url(auth_info['uid'], _local_url(redirect))
        if '/web/login' in final_url and '/web/login/totp' not in final_url:
            final_url = '/'
        return {'status': 'success', 'redirect': final_url}
