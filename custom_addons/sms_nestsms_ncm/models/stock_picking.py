# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models

SMS_TEMPLATES = {
    'out_for_delivery': 'sms_nestsms_ncm.sms_template_ncm_out_for_delivery',
    'delivered': 'sms_nestsms_ncm.sms_template_ncm_delivered',
}


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    ncm_sms_sent_states = fields.Char(
        copy=False, readonly=True,
        help="Technical: NCM stages the customer was already texted about, comma-separated.",
    )

    def _ncm_set_current_status(self, status, date=None):
        old_state = self.ncm_state
        res = super()._ncm_set_current_status(status, date=date)
        state = self.ncm_state
        if state != old_state and state in SMS_TEMPLATES and self.carrier_id.ncm_notify_customer_sms:
            self._ncm_sms_customer(state)
        return res

    def _ncm_sms_customer(self, state):
        """Text the customer about `state`, at most once per parcel: a redelivery attempt
        or NCM resending a status doesn't text them again."""
        self.ensure_one()
        sent = set(filter(None, (self.ncm_sms_sent_states or '').split(',')))
        if state in sent:
            return
        customer = self.sale_id.partner_id or self._ncm_customer()
        if self._sms_nestsms_notify(SMS_TEMPLATES[state], customer):
            self.sudo().ncm_sms_sent_states = ','.join(sorted(sent | {state}))
