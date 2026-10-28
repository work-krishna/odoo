from odoo import fields, models


class ProductProduct(models.Model):
    _inherit = 'product.product'

    is_variant_out_of_stock = fields.Boolean(
        string='Out of Stock',
        help="Out of stock on the website, whatever its quantity: the variant can't be chosen nor added to the cart. "
             "The product is out of stock when all its variants are.",
    )

    def _is_sold_out(self):
        """ Override of `website_sale_stock`: a variant marked out of stock is sold out, even if its inventory isn't
        tracked.
        """
        return self.is_variant_out_of_stock or super()._is_sold_out()
