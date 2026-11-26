# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import models


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    def _send_confirmation_email(self):
        # Core stock_sms texts at once, inside the validation, without the opt-out list or
        # the Nepali-number check. Queue it through NestSMS like every other customer text.
        super(StockPicking, self.with_context(skip_sms=True))._send_confirmation_email()
        if self.env.context.get('skip_sms'):
            return
        for picking in self.filtered(lambda p: p.company_id._get_text_validation('sms') and p.picking_type_id.code == 'outgoing'):
            template = picking.company_id.sudo().stock_sms_confirmation_template_id
            picking._sms_nestsms_notify(template, picking._sms_nestsms_customer())

    def _sms_nestsms_customer(self):
        """The person to text. For collect-at-a-pickup-point orders Odoo replaces the delivery
        address with a contact named after the pickup point; the customer is its parent."""
        self.ensure_one()
        partner = self.partner_id
        if 'is_pickup_location' in partner._fields and partner.is_pickup_location and partner.parent_id:
            return partner.parent_id
        return partner
