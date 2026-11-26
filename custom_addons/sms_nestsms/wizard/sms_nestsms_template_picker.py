# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import _, api, fields, models
from odoo.fields import Command

from odoo.addons.sms_nestsms.models.sms_nestsms_otp import OTP_PURPOSES, otp_template_values, render_otp_template


class SmsNestsmsTemplatePicker(models.TransientModel):
    """Settings > Choose...: the organisation's NestSMS OTP templates, to pick one for a
    purpose instead of pasting its ID."""
    _name = 'sms.nestsms.template.picker'
    _description = "Choose a NestSMS OTP Template"

    company_id = fields.Many2one('res.company', required=True, readonly=True)
    purpose = fields.Selection(OTP_PURPOSES, required=True, readonly=True)
    line_ids = fields.One2many('sms.nestsms.template.picker.line', 'picker_id', readonly=True)
    error = fields.Char(readonly=True)

    @api.model
    def _action_open(self, company, purpose):
        picker = self.create({'company_id': company.id, 'purpose': purpose})
        picker._fetch()
        return picker._action_reopen()

    def _action_reopen(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Choose the OTP Template: %s", dict(self._fields['purpose']._description_selection(self.env))[self.purpose]),
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'views': [(False, 'form')],
            'target': 'new',
        }

    def _fetch(self):
        self.ensure_one()
        company = self.company_id
        templates, error = company._sms_nestsms_api()._nestsms_list_templates(message_type='otp')
        current = company._sms_otp_template(self.purpose)
        prefix = f"{company.sms_brand_name}:" if company.sms_brand_name else None

        def brand_ok(template):  # judged on the text as customers get it
            content = template.get('content') or ''
            values, _unknown = otp_template_values(content, self.purpose, company.sms_brand_name, '123456')
            return bool(prefix) and render_otp_template(content, values).startswith(prefix)

        # Usable ones first (approved, with the brand prefix), then by name.
        templates.sort(key=lambda t: (not t.get('is_verified'), not brand_ok(t), (t.get('name') or '').lower()))
        self.line_ids.unlink()
        self.write({
            'error': error,
            'line_ids': [Command.create({
                'sequence': index,
                'nestsms_id': str(template.get('id') or ''),
                'name': template.get('name') or _("(no name)"),
                'content': template.get('content') or '',
                'is_verified': bool(template.get('is_verified')),
                'is_current': str(template.get('id')) == current,
                'is_brand_ok': brand_ok(template),
            }) for index, template in enumerate(templates) if template.get('id')],
        })

    def action_refresh(self):
        self._fetch()
        return self._action_reopen()


class SmsNestsmsTemplatePickerLine(models.TransientModel):
    _name = 'sms.nestsms.template.picker.line'
    _description = "NestSMS OTP Template"
    _order = 'sequence, id'

    picker_id = fields.Many2one('sms.nestsms.template.picker', required=True, ondelete='cascade')
    sequence = fields.Integer()
    nestsms_id = fields.Char(string="Template ID", required=True)
    name = fields.Char()
    content = fields.Text()
    is_verified = fields.Boolean(string="Approved")
    is_current = fields.Boolean(string="In Use")
    is_brand_ok = fields.Boolean(help="Starts with the SMS brand name and a colon, as NTA requires.")

    def action_use(self):
        """Use this template for the picker's purpose, then check it with NestSMS: codes are
        switched on only if it passes."""
        self.ensure_one()
        picker = self.picker_id
        company, purpose = picker.company_id, picker.purpose
        company.write({f'sms_otp_{purpose}': True, f'sms_otp_{purpose}_template': self.nestsms_id})
        content, problems = company._sms_otp_check_template(purpose)
        if problems:
            company._sms_otp_set_approved(purpose, False)
            params = {
                'type': 'warning', 'sticky': True,
                'message': _("Template selected, but SMS codes stay off: %s", ' '.join(problems)),
            }
        else:
            company._sms_otp_set_approved(purpose, self.nestsms_id, content)
            params = {'type': 'success', 'message': _("Template selected and approved: SMS codes are on.")}
        params['next'] = {'type': 'ir.actions.act_window_close'}
        return {'type': 'ir.actions.client', 'tag': 'display_notification', 'params': params}
