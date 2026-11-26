# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging

from odoo import _, api, models

from odoo.addons.sms_nestsms.models.sms_nestsms_otp import OTP_VALIDITY
from odoo.addons.sms_nestsms.tools.sms_api import nepal_mobile

_logger = logging.getLogger(__name__)


class ResUsers(models.Model):
    _inherit = 'res.users'

    def _signup_sms_number(self):
        """The Nepali mobile to text the activation code to, or False to email it."""
        self.ensure_one()
        if not self.company_id._sms_otp_enabled('signup'):
            return False
        return nepal_mobile(self.partner_id.phone)

    @api.model
    def _signup_validity(self):
        # The approved NestSMS template states how long the code lasts.
        validity = super()._signup_validity()
        if self.env.company._sms_otp_enabled('signup'):
            validity = min(validity, int(OTP_VALIDITY.total_seconds() // 60))
        return validity

    def _signup_deliver_verification(self, code, link, minutes):
        number = self._signup_sms_number()
        if number:
            otp, error = self.env['sms.nestsms.otp']._nestsms_send('signup', number, self.company_id, code=code)
            if otp:
                return 'sms'
            # Over the hourly cap, NestSMS down...: email it rather than leave them stuck.
            _logger.info("Sign-up code for user %s goes by email: %s", self.id, error)
        return super()._signup_deliver_verification(code, link, minutes)

    def _signup_check_code(self, code):
        channel = self._signup_channel()  # read first: activation deletes the pending code
        super()._signup_check_code(code)
        if channel == 'sms':
            # Only the phone could have received this code: the number is proven.
            number = nepal_mobile(self.partner_id.phone)
            self.partner_id._sms_mark_phone_verified(number)
            self.env['sms.nestsms.otp'].sudo().search(
                [('purpose', '=', 'signup'), ('number', '=', number), ('state', '=', 'sent')], limit=1,
            ).state = 'verified'

    def _signup_sent_to(self):
        if self._signup_channel() == 'sms':
            number = nepal_mobile(self.partner_id.phone) or ''
            return f"{number[:3]}*****{number[-2:]}"
        return super()._signup_sent_to()

    def _signup_message(self, kind):
        if self._signup_channel() != 'sms':
            return super()._signup_message(kind)
        return {
            'resent': _("We texted you a new code."),
            'cooldown': _("We texted you a code less than a minute ago. Please wait a moment before asking again."),
            'expired': _("Your previous code has expired, so we texted you a new one."),
        }[kind]
