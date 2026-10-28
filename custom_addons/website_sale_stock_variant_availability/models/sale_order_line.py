from odoo import models


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    def _check_availability(self):
        """ Override of `website_sale_stock`: a variant marked out of stock after being added to the cart can't be paid
        for.
        """
        self.ensure_one()
        if self.product_id.is_variant_out_of_stock:
            self._set_shop_warning_stock(self.product_uom_qty, 0)
            return False
        return super()._check_availability()
