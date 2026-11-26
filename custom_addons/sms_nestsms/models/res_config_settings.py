# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import _, api, fields, models
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
    # Whether the template ID shown is the one Check approved (codes only go out then).
    sms_otp_login_approved = fields.Boolean(compute='_compute_sms_otp_approved')
    sms_otp_signup_approved = fields.Boolean(compute='_compute_sms_otp_approved')
    sms_otp_checkout_approved = fields.Boolean(compute='_compute_sms_otp_approved')
    sms_otp_emi_approved = fields.Boolean(compute='_compute_sms_otp_approved')

    @api.depends('company_id', *(f'sms_otp_{purpose}_template' for purpose, _label in OTP_PURPOSES))
    def _compute_sms_otp_approved(self):
        for settings in self:
            for purpose, _label in OTP_PURPOSES:
                settings[f'sms_otp_{purpose}_approved'] = settings.company_id._sms_otp_approved(
                    purpose, settings[f'sms_otp_{purpose}_template'] or '',
                )

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

    def _sms_otp_context_purpose(self):
        purpose = self.env.context.get('sms_otp_purpose')
        if purpose not in dict(OTP_PURPOSES):
            raise UserError(_("Unknown purpose."))
        return purpose

    def action_sms_otp_choose_template(self):
        """Settings button: pick the purpose's template from those in NestSMS."""
        self.ensure_one()
        purpose = self._sms_otp_context_purpose()
        if not self.company_id.sudo().sms_nestsms_api_key:
            raise UserError(_("Enter the NestSMS API key first."))
        return self.env['sms.nestsms.template.picker']._action_open(self.company_id, purpose)

    def action_sms_otp_check_template(self):
        """Settings button next to each OTP template ID (context: sms_otp_purpose)."""
        self.ensure_one()
        purpose = self._sms_otp_context_purpose()
        company = self.company_id
        content, problems = company._sms_otp_check_template(purpose)
        if problems:
            company._sms_otp_set_approved(purpose, False)
            return self._sms_nestsms_notification(
                'warning', ' '.join(problems) + ' ' + _("SMS codes for this stay off."), sticky=True, reload=True,
            )
        company._sms_otp_set_approved(purpose, company._sms_otp_template(purpose), content)
        return self._sms_nestsms_notification('success', _("Approved: SMS codes are on. Text: %s", content), reload=True)

    def _sms_nestsms_notification(self, kind, message, sticky=False, reload=False):
        params = {'type': kind, 'message': message, 'sticky': sticky}
        if reload:  # show the new approval status
            params['next'] = {'type': 'ir.actions.client', 'tag': 'soft_reload'}
        return {'type': 'ir.actions.client', 'tag': 'display_notification', 'params': params}
