import re
import secrets
from datetime import timedelta

from werkzeug.urls import url_encode

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import consteq
from odoo.tools.misc import hmac

VALIDITY_PARAM = 'auth_signup_email_otp.validity_minutes'
DEFAULT_VALIDITY = 15  # minutes
RESEND_COOLDOWN = timedelta(seconds=60)
MAX_ATTEMPTS = 5


def _new_code():
    return f"{secrets.randbelow(10 ** 6):06d}"


def _new_token():
    return secrets.token_urlsafe(32)


def _digest(env, scope, message):
    return hmac(env(su=True), f'auth_signup_email_otp.{scope}', message)


class ResUsers(models.Model):
    _inherit = 'res.users'

    signup_email_verified = fields.Boolean(
        string='Email Verified', default=True, copy=False,
        help="Unticked for accounts created through the website sign-up until the person enters the "
             "code or opens the link emailed to them; they cannot log in before that.",
    )

    # ------------------------------------------------------------------
    # Sign-up and login
    # ------------------------------------------------------------------

    @api.model
    def signup(self, values, token=None):
        login, password = super().signup(values, token)
        user = self.search(self._get_login_domain(login), order=self._get_login_order(), limit=1)
        if token:
            # An invitation or password reset link was emailed: the address is proven.
            if user and not user.signup_email_verified:
                user._signup_mark_verified()
        elif user:
            user.signup_email_verified = False
            user._signup_send_verification()
        return login, password

    def _mfa_url(self):
        # The address comes first; two-factor authentication, if any, follows once it is verified.
        if not self.sudo().signup_email_verified:
            return '/web/signup/verify'
        return super()._mfa_url()

    def _rpc_api_keys_only(self):
        # No password logins through the API either before activation.
        return not self.sudo().signup_email_verified or super()._rpc_api_keys_only()

    # ------------------------------------------------------------------
    # Code and link
    # ------------------------------------------------------------------

    @api.model
    def _signup_validity(self):
        """Minutes an activation code and link stay valid (Settings)."""
        try:
            minutes = int(self.env['ir.config_parameter'].sudo().get_param(VALIDITY_PARAM, DEFAULT_VALIDITY))
        except ValueError:
            minutes = DEFAULT_VALIDITY
        return max(minutes, 1)

    def _signup_pending(self):
        self.ensure_one()
        return self.env['auth.signup.verification'].sudo().search([('user_id', '=', self.id)])

    def _signup_has_valid_code(self):
        pending = self._signup_pending()
        return bool(pending) and pending.attempts < MAX_ATTEMPTS and pending.expires_at > fields.Datetime.now()

    def _signup_send_verification(self):
        """Email a new code and activation link, replacing the previous ones.
        Returns False, sending nothing, when the last email is under a minute old."""
        self.ensure_one()
        pending = self._signup_pending()
        now = fields.Datetime.now()
        if pending and now - pending.sent_at < RESEND_COOLDOWN:
            return False
        code, token, minutes = _new_code(), _new_token(), self._signup_validity()
        vals = {
            'user_id': self.id,
            'code_hash': _digest(self.env, 'code', f'{self.id}:{code}'),
            'token_hash': _digest(self.env, 'link', token),
            'expires_at': now + timedelta(minutes=minutes),
            'sent_at': now,
            'attempts': 0,
        }
        if pending:
            pending.write(vals)
        else:
            self.env['auth.signup.verification'].sudo().create(vals)
        link = f"{self.get_base_url()}/web/signup/activate?{url_encode({'token': token})}"
        template = self.env.ref('auth_signup_email_otp.mail_template_signup_verification')
        template.sudo().with_context(signup_code=code, signup_link=link, signup_validity=minutes).send_mail(
            self.id, force_send=True,
        )
        return True

    def _signup_check_code(self, code):
        """Activate the account if ``code`` is the one last emailed; otherwise
        raise a UserError saying why not."""
        self.ensure_one()
        pending = self._signup_pending()
        if not pending or pending.attempts >= MAX_ATTEMPTS:
            raise UserError(_("This code can no longer be used. Send yourself a new one."))
        if pending.expires_at <= fields.Datetime.now():
            raise UserError(_("This code has expired. Send yourself a new one."))
        code = re.sub(r'\s', '', code or '')
        if not consteq(pending.code_hash, _digest(self.env, 'code', f'{self.id}:{code}')):
            pending.attempts += 1
            left = MAX_ATTEMPTS - pending.attempts
            if not left:
                raise UserError(_("That code is not right, and it cannot be used any more. Send yourself a new one."))
            raise UserError(_("That code is not right. %(left)s tries left.", left=left))
        self._signup_mark_verified()

    @api.model
    def _signup_check_link(self, token):
        """Account of an activation link, now activated; raises a UserError if
        the link is unknown, replaced by a newer one, or expired."""
        pending = self.env['auth.signup.verification'].sudo().search(
            [('token_hash', '=', _digest(self.env, 'link', token or ''))], limit=1)
        if not token or not pending:
            raise UserError(_("This activation link is not valid, or a newer one was sent since."))
        if pending.expires_at <= fields.Datetime.now():
            raise UserError(_("This activation link has expired."))
        user = pending.user_id
        user._signup_mark_verified()
        return user

    def _signup_mark_verified(self):
        users = self.sudo().filtered(lambda u: not u.signup_email_verified)
        users.signup_email_verified = True
        self.env['auth.signup.verification'].sudo().search([('user_id', 'in', self.ids)]).unlink()
        # The welcome email auth_signup sends at sign-up was held back until now.
        welcome = self.env.ref('auth_signup.mail_template_user_signup_account_created', raise_if_not_found=False)
        for user in users.filtered(lambda u: u.share and u.email):
            if welcome:
                welcome.sudo().send_mail(user.id, force_send=True)

    def action_signup_send_verification(self):
        """Settings > Users: email a new activation code to accounts not activated yet."""
        for user in self.filtered(lambda u: not u.signup_email_verified):
            user._signup_send_verification()
        return True
