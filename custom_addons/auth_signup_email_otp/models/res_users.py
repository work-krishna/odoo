"""Website sign-ups activate their account with a one-time code (or the emailed link).

Codes (generation, hashing, expiry, wrong tries, resend cooldown, rate limits) come from the
one-time-code engine, auth_otp. A sign-up gets a code by email (with a link) and, where SMS
codes are on for sign-up, a different code by SMS. Either one activates the account and closes
the other, and the one used says what was proven:

- the email code or link: the email address (`signup_email_verified`). The mobile number is
  confirmed later, e.g. at checkout;
- the SMS code: the mobile number (see sms_nestsms_signup). The account works, and the website
  asks the person to confirm their email address too, without blocking anything.
"""
from datetime import timedelta

from werkzeug.urls import url_encode

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from odoo.addons.auth_otp.models.auth_otp import mask_email

VALIDITY_PARAM = 'auth_signup_email_otp.validity_minutes'
DEFAULT_VALIDITY = 15  # minutes
PURPOSE = 'signup'
VERIFY_EMAIL = 'verify_email'  # confirming the address of an account activated by SMS


class ResUsers(models.Model):
    _inherit = 'res.users'

    signup_activated = fields.Boolean(
        string='Account Activated', default=True, copy=False,
        help="Unticked for accounts created through the website sign-up until the person enters a code "
             "sent to them (by email or SMS) or opens the emailed link; they cannot log in before that.",
    )
    signup_email_verified = fields.Boolean(
        string='Email Verified', default=True, copy=False,
        help="Unticked for accounts created through the website sign-up until the person enters the "
             "code or opens the link emailed to them. An account activated with the SMS code works, "
             "and the website asks them to confirm their email address.",
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
            if user and not (user.signup_activated and user.signup_email_verified):
                user._signup_mark_verified()
        elif user:
            user.write({'signup_activated': False, 'signup_email_verified': False})
            user._signup_send_verification()
        return login, password

    def _mfa_url(self):
        # Activation comes first; two-factor authentication, if any, follows.
        if not self.sudo().signup_activated:
            return '/web/signup/verify'
        return super()._mfa_url()

    def _rpc_api_keys_only(self):
        # No password logins through the API either before activation.
        return not self.sudo().signup_activated or super()._rpc_api_keys_only()

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
        """Send new activation codes: one to the account's email address (with an activation
        link) and, where SMS codes are on for sign-up, another to its mobile number. They
        replace the previous ones. Returns ``(sent, error)``."""
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
        """Activate the account if ``code`` is one of its live codes (emailed or texted);
        otherwise raise a UserError saying why not. Returns the auth.otp record, whose
        `verified_by` says which code it was."""
        self.ensure_one()
        otp, error = self.env['auth.otp']._otp_verify(PURPOSE, code, user=self)
        if not otp:
            raise UserError(error)
        self._signup_mark_verified(otp)
        return otp

    @api.model
    def _signup_check_link(self, token):
        """Account of an activation link, now activated; raises a UserError if the link is
        unknown, replaced by a newer one, or expired."""
        otp, error = self.env['auth.otp']._otp_verify_link(PURPOSE, token)
        if not otp:
            raise UserError(error)
        user = otp.user_id
        user._signup_mark_verified(otp)
        return user

    def _signup_mark_verified(self, otp=None):
        """Activate the accounts. `otp` is the sign-up code that did it: its email code or link
        also proves the email address, its SMS code the mobile number (sms_nestsms_signup).
        Without one (an invitation or password-reset link, which came by email) the email
        address counts as proven."""
        self.sudo().filtered(lambda u: not u.signup_activated).signup_activated = True
        for user in self:
            self.env['auth.otp']._otp_close(PURPOSE, user=user)
        if not otp or otp.verified_by == 'email':
            self._signup_mark_email_verified()

    def _signup_mark_email_verified(self):
        users = self.sudo().filtered(lambda u: not u.signup_email_verified)
        users.signup_email_verified = True
        for user in self:
            self.env['auth.otp']._otp_close(VERIFY_EMAIL, user=user)
        # The welcome email auth_signup sends at sign-up was held back until now.
        welcome = self.env.ref('auth_signup.mail_template_user_signup_account_created', raise_if_not_found=False)
        for user in users.filtered(lambda u: u.share and u.email):
            if welcome:
                welcome.sudo().send_mail(user.id, force_send=True)

    # ------------------------------------------------------------------
    # Confirming the email address later (accounts activated by SMS)
    # ------------------------------------------------------------------

    def _signup_email_unverified(self):
        """Whether to ask this (logged-in) person to confirm their email address: their
        account works, activated by SMS, but the address isn't proven yet."""
        self.ensure_one()
        user = self.sudo()
        return bool(user.signup_activated and not user.signup_email_verified and user.email and not user._is_public())

    def _verify_email_send(self):
        """Email a code and a link that confirm the address. Returns ``(sent, error)``."""
        self.ensure_one()
        result = self.env['auth.otp']._otp_issue(
            VERIFY_EMAIL, user=self, email=self.email, company=self.company_id,
            with_link=True, email_sender=self._verify_email_sender,
        )
        return bool(result['otp']), result['error']

    def _verify_email_sender(self, otp, code, token):
        link = f"{self.get_base_url()}/web/verify-email?{url_encode({'token': token})}"
        template = self.env.ref('auth_signup_email_otp.mail_template_verify_email')
        template.sudo().with_context(signup_code=code, signup_link=link, signup_validity=otp._otp_minutes()).send_mail(
            self.id, force_send=True,
        )

    def _verify_email_pending(self):
        self.ensure_one()
        return self.env['auth.otp']._otp_live(VERIFY_EMAIL, user=self)

    def _verify_email_check_code(self, code):
        """Confirm the email address if ``code`` is the one emailed; otherwise raise a
        UserError saying why not."""
        self.ensure_one()
        otp, error = self.env['auth.otp']._otp_verify(VERIFY_EMAIL, code, user=self)
        if not otp:
            raise UserError(error)
        self._verify_email_confirm(otp)

    @api.model
    def _verify_email_check_link(self, token):
        """Account whose email address the link confirms, now confirmed; raises a UserError
        if the link is unknown, replaced by a newer one, or expired."""
        otp, error = self.env['auth.otp']._otp_verify_link(VERIFY_EMAIL, token)
        if not otp:
            raise UserError(error)
        otp.user_id._verify_email_confirm(otp)
        return otp.user_id

    def _verify_email_confirm(self, otp):
        user = self.sudo()
        if (otp.email or '') != (user.email or '').strip().lower():
            raise UserError(_("Your email address changed since we sent this code. Ask for a new one."))
        user._signup_mark_email_verified()

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
                'resent': _("We sent you new codes by email and SMS."),
                'expired': _("Your previous codes have expired, so we sent you new ones by email and SMS."),
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
        for user in self.filtered(lambda u: not u.signup_activated):
            user._signup_send_verification()
        return True


class AuthOtp(models.Model):
    _inherit = 'auth.otp'

    @api.model
    def _otp_policy(self, purpose, company):
        policy = super()._otp_policy(purpose, company)
        if purpose in (PURPOSE, VERIFY_EMAIL):
            # Settings > Sign-up Activation. A texted code may be capped shorter (its approved
            # message states the minutes): see auth.otp._otp_sms_max_validity.
            policy = dict(policy, validity=timedelta(minutes=self.env['res.users']._signup_validity()))
        if purpose == VERIFY_EMAIL:
            policy['channels'] = ('email',)
        return policy
