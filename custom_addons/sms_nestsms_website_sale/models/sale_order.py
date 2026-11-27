# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import _, fields, models
from odoo.exceptions import ValidationError


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    sms_verified_phone = fields.Char(
        string="Verified Mobile", related='partner_id.sms_verified_phone', groups='base.group_user',
        help="The mobile number the customer proved with an SMS code, at checkout or at sign-up. "
             "The delivery address may carry another number, e.g. when buying for someone else.",
    )

    def _sms_checkout_company(self):
        self.ensure_one()
        return (self.website_id.company_id or self.company_id).sudo()

    def _sms_checkout_needs_verification(self):
        """Whether the buyer must still prove a mobile number by SMS before ordering.

        Only website orders, and only when Settings require it. Then it is strict: the order
        can't go through until the buyer has proven a number, even while codes can't be sent.
        The buyer is the order's customer (the signed-in account, or the guest's own contact).
        A number proven before, at sign-up or on an earlier order, counts, and delivery
        addresses may carry any number."""
        self.ensure_one()
        if not self.website_id or not self._sms_checkout_company().sms_otp_checkout:
            return False
        return not self.partner_id.sudo().sms_verified_phone

    def _sms_checkout_codes_available(self):
        """Whether checkout codes can be texted right now (API key set, template approved)."""
        self.ensure_one()
        return self._sms_checkout_company()._sms_otp_enabled('checkout')

    def _check_cart_is_ready_to_be_paid(self):
        # Every way to pay or confirm a cart goes through here: the payment route, free
        # orders and express checkout.
        for order in self:
            if order._sms_checkout_needs_verification():
                raise ValidationError(_("Please confirm your mobile number with the SMS code first."))
        return super()._check_cart_is_ready_to_be_paid()
