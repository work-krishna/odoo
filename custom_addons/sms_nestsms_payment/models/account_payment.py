# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    sms_receipt_sent = fields.Boolean(copy=False, readonly=True)

    def action_post(self):
        """Text the customer once their payment is confirmed: online payments (eSewa, Khalti,
        connectIPS, Fonepay...) as the gateway verifies them, EMI down payments and
        installments, and payments staff register by hand."""
        res = super().action_post()
        for payment in self.filtered(lambda p: p._sms_receipt_due()):
            if payment._sms_nestsms_notify('sms_nestsms_payment.sms_template_payment_received', payment.partner_id):
                payment.sudo().sms_receipt_sent = True
        return res

    def _sms_receipt_due(self):
        self.ensure_one()
        return (
            self.state in ('in_process', 'paid')
            and self.payment_type == 'inbound'
            and self.partner_type == 'customer'
            and self.partner_id
            and self.amount > 0
            and not self.sms_receipt_sent  # once, even if reset to draft and posted again
            and self.company_id.sms_notify_payment_received
            # Point of Sale closing entries aren't a payment the customer just made.
            and not ('pos_session_id' in self._fields and self.pos_session_id)
        )
