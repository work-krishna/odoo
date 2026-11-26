# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import models


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def _sms_checkout_needs_verification(self):
        """Whether the shopper must confirm their mobile number by SMS before paying: website
        orders only, once per customer and number (a number proven at sign-up counts)."""
        self.ensure_one()
        company = self.website_id.company_id or self.company_id
        if not self.website_id or not company._sms_otp_enabled('checkout'):
            return False
        partner = self.partner_id
        return not partner._sms_phone_is_verified(partner.phone)
