"""Website sign-ups activate their account with a one-time code (or the emailed link).

The code itself (generation, hashing, expiry, wrong tries, resend cooldown, rate limits) comes
from the one-time-code engine, auth_otp: ONE code per request, emailed to the account's
address and, where SMS codes are on for sign-up, texted to its mobile number too. Either copy
activates the account.
"""
from datetime import timedelta

from werkzeug.urls import url_encode

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from odoo.addons.auth_otp.models.auth_otp import mask_email

VALIDITY_PARAM = 'auth_signup_email_otp.validity_minutes'
DEFAULT_VALIDITY = 15  # minutes
PURPOSE = 'signup'


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
    # Code and link (auth_otp)
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
        """The activation code waiting to be entered (an auth.otp record), if any."""
        self.ensure_one()
        return self.env['auth.otp']._otp_live(PURPOSE, user=self)

    def _signup_has_valid_code(self):
        pending = self._signup_pending()
        return bool(pending) and pending.expires_at > fields.Datetime.now()

    def _signup_send_verification(self):
        """Send one new activation code to the account's email address (with an activation
        link) and, where SMS codes are on for sign-up, the same code to its mobile number. It
        replaces the previous code. Returns ``(sent, error)``."""
        self.ensure_one()
        result = self.env['auth.otp']._otp_issue(
            PURPOSE, user=self, email=self.email, phone=self.partner_id.phone, company=self.company_id,
            with_link=True, email_sender=self._signup_email_sender,
        )
        return bool(result['otp']), result['error']

    def _signup_email_sender(self, otp, code, token):
        link = f"{self.get_base_url()}/web/signup/activate?{url_encode({'token': token})}"
        template = self.env.ref('auth_signup_email_otp.mail_template_signup_verification')
        template.sudo().with_context(signup_code=code, signup_link=link, signup_validity=otp._otp_minutes()).send_mail(
            self.id, force_send=True,
        )

    def _signup_check_code(self, code):
        """Activate the account if ``code`` is the live one; otherwise raise a UserError
        saying why not."""
        self.ensure_one()
        otp, error = self.env['auth.otp']._otp_verify(PURPOSE, code, user=self)
        if not otp:
            raise UserError(error)
        self._signup_mark_verified()

    @api.model
    def _signup_check_link(self, token):
        """Account of an activation link, now activated; raises a UserError if the link is
        unknown, replaced by a newer one, or expired."""
        otp, error = self.env['auth.otp']._otp_verify_link(PURPOSE, token)
        if not otp:
            raise UserError(error)
        user = otp.user_id
        user._signup_mark_verified()
        return user

    def _signup_mark_verified(self):
        users = self.sudo().filtered(lambda u: not u.signup_email_verified)
        users.signup_email_verified = True
        for user in self:
            self.env['auth.otp']._otp_close(PURPOSE, user=user)
        # The welcome email auth_signup sends at sign-up was held back until now.
        welcome = self.env.ref('auth_signup.mail_template_user_signup_account_created', raise_if_not_found=False)
        for user in users.filtered(lambda u: u.share and u.email):
            if welcome:
                welcome.sudo().send_mail(user.id, force_send=True)

    def _signup_sent_to(self):
        """Where the live code went, masked for display: {'email': ..., 'sms': ...}."""
        self.ensure_one()
        pending = self._signup_pending()
        return pending._otp_sent_to() if pending else {'email': mask_email(self.email)}

    def _signup_message(self, kind):
        """Text for the verify page: 'resent' (new code on its way) or 'expired' (old code
        dead, new one sent)."""
        self.ensure_one()
        sent_to = self._signup_sent_to()
        if sent_to.get('email') and sent_to.get('sms'):
            return {
                'resent': _("We sent you a new code by email and SMS."),
                'expired': _("Your previous code has expired, so we sent you a new one by email and SMS."),
            }[kind]
        if sent_to.get('sms'):
            return {
                'resent': _("We texted you a new code."),
                'expired': _("Your previous code has expired, so we texted you a new one."),
            }[kind]
        return {
            'resent': _("We emailed you a new code and link."),
            'expired': _("Your previous code has expired, so we emailed you a new one."),
        }[kind]

    def action_signup_send_verification(self):
        """Settings > Users: send a new activation code to accounts not activated yet."""
        for user in self.filtered(lambda u: not u.signup_email_verified):
            user._signup_send_verification()
        return True


class AuthOtp(models.Model):
    _inherit = 'auth.otp'

    @api.model
    def _otp_policy(self, purpose, company):
        policy = super()._otp_policy(purpose, company)
        if purpose == PURPOSE:
            # Settings > Sign-up Activation. A texted code may be capped shorter (its approved
            # message states the minutes): see auth.otp._otp_sms_max_validity.
            policy = dict(policy, validity=timedelta(minutes=self.env['res.users']._signup_validity()))
        return policy
