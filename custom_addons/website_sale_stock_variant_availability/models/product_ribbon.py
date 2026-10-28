from odoo import models


class ProductRibbon(models.Model):
    _inherit = 'product.ribbon'

    def _is_applicable_for(self, product, price_data):
        """ Override of `website_sale_stock`: the "when out of stock" ribbon is also for the variants marked out of
        stock, even if their inventory isn't tracked.
        """
        return super()._is_applicable_for(product, price_data) or bool(
            product
            and product._name == 'product.product'
            and self.assign == 'out_of_stock'
            and product.is_variant_out_of_stock
        )
