# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import _, fields, models
from odoo.exceptions import UserError


class SmsNestsmsTest(models.TransientModel):
    _name = 'sms.nestsms.test'
    _description = "Send a NestSMS Test Message"

    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    number = fields.Char(string="Mobile Number", required=True, help="A Nepali mobile number, e.g. 98XXXXXXXX.")
    body = fields.Text(string="Message", required=True, default=lambda self: self._default_body())

    def _default_body(self):
        company = self.env['res.company'].browse(self.env.context.get('default_company_id')) or self.env.company
        brand = company.sms_brand_name or company.name
        return _("%s: Test message from Odoo. Texts to customers now go out through NestSMS.", brand)

    def action_send(self):
        """Send straight away (not through the queue) and say what NestSMS answered."""
        self.ensure_one()
        sms_api = self.company_id._get_sms_api_class()(self.env)
        sms_api._set_company(self.company_id)
        result = sms_api._send_sms_batch([{
            'content': self.body,
            'numbers': [{'uuid': 'nestsms-test', 'number': self.number}],
        }])[0]
        if result['state'] != 'success':
            raise UserError(result.get('failure_reason') or _("NestSMS did not accept the SMS (%s).", result['state']))
        message = _("NestSMS accepted the SMS to %s.", self.number)
        if result.get('nestsms_message_id'):
            message += ' ' + _("Message ID: %s", result['nestsms_message_id'])
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'type': 'success',
                'message': message,
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }
