# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import _, fields, models
from odoo.exceptions import UserError

from odoo.addons.sms_nestsms.models.sms_nestsms_otp import OTP_PURPOSES


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    sms_nestsms_api_key = fields.Char(
        related='company_id.sms_nestsms_api_key', readonly=False, groups='base.group_system',
    )
    sms_brand_name = fields.Char(related='company_id.sms_brand_name', readonly=False)

    sms_otp_login = fields.Boolean(related='company_id.sms_otp_login', readonly=False)
    sms_otp_login_template = fields.Char(related='company_id.sms_otp_login_template', readonly=False)
    sms_otp_signup = fields.Boolean(related='company_id.sms_otp_signup', readonly=False)
    sms_otp_signup_template = fields.Char(related='company_id.sms_otp_signup_template', readonly=False)
    sms_otp_checkout = fields.Boolean(related='company_id.sms_otp_checkout', readonly=False)
    sms_otp_checkout_template = fields.Char(related='company_id.sms_otp_checkout_template', readonly=False)
    sms_otp_emi = fields.Boolean(related='company_id.sms_otp_emi', readonly=False)
    sms_otp_emi_template = fields.Char(related='company_id.sms_otp_emi_template', readonly=False)

    def action_open_sms_nestsms_test(self):
        self.ensure_one()
        return {
            'name': _("Send a Test SMS"),
            'type': 'ir.actions.act_window',
            'res_model': 'sms.nestsms.test',
            'view_mode': 'form',
            'views': [(False, 'form')],
            'target': 'new',
            'context': {'default_company_id': self.company_id.id},
        }

    def action_sms_nestsms_balance(self):
        self.ensure_one()
        reply = self.company_id._sms_nestsms_api()._nestsms_get_balance()
        if not reply.ok:
            raise UserError(reply.reason)
        data = reply.data
        message = _(
            "Balance: %(currency)s %(balance)s, about %(count)s messages.",
            currency=data.get('currency') or 'NPR', balance=data.get('balance'), count=data.get('messages_remaining'),
        )
        return self._sms_nestsms_notification('info', message)

    def action_sms_otp_check_template(self):
        """Settings button next to each OTP template ID (context: sms_otp_purpose)."""
        self.ensure_one()
        purpose = self.env.context.get('sms_otp_purpose')
        if purpose not in dict(OTP_PURPOSES):
            raise UserError(_("Unknown purpose."))
        content, problems = self.company_id._sms_otp_check_template(purpose)
        if problems:
            return self._sms_nestsms_notification('warning', ' '.join(problems), sticky=True)
        return self._sms_nestsms_notification('success', _("Approved and ready: %s", content))

    def _sms_nestsms_notification(self, kind, message, sticky=False):
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {'type': kind, 'message': message, 'sticky': sticky},
        }
