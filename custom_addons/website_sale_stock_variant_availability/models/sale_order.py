from odoo import models


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def _verify_updated_quantity(self, order_line, product_id, new_qty, uom_id, **kwargs):
        """ Override of `website_sale_stock`: the variants marked out of stock can't be added to the cart """
        product = self.env['product.product'].browse(product_id)
        if product.is_variant_out_of_stock and new_qty > 0:
            if order_line:
                warning = self.env._(
                    "Some products became unavailable and your cart has been updated. We're sorry for the"
                    " inconvenience."
                )
            else:
                warning = self.env._(
                    "%(product_name)s has not been added to your cart since it is not available.",
                    product_name=product.name,
                )
            return 0, warning
        return super()._verify_updated_quantity(order_line, product_id, new_qty, uom_id, **kwargs)
