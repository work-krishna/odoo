# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    sms_confirmation_sent = fields.Boolean(copy=False, readonly=True)

    def _action_confirm(self):
        res = super()._action_confirm()
        # Once per order: confirming again after a cancel doesn't text the customer twice.
        for order in self.filtered(lambda o: not o.sms_confirmation_sent and o.company_id.sms_notify_order_confirmed):
            if order._sms_nestsms_notify('sms_nestsms_sale.sms_template_order_confirmed', order.partner_id):
                order.sudo().sms_confirmation_sent = True
        return res
