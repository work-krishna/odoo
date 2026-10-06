from odoo import fields, models


class ProductProduct(models.Model):
    _inherit = 'product.product'

    is_variant_published = fields.Boolean(
        string='Variant Published', default=True,
        help="Show this variant on the website. Its product must be published too. "
             "Unticked, the variant can't be chosen nor added to the cart on the website.",
    )

    def write(self, vals):
        res = super().write(vals)
        if 'is_variant_published' in vals:
            # `_get_first_possible_variant_id` depends on it on the website
            self.env.registry.clear_cache()
        return res

    def _is_add_to_cart_allowed(self):
        """ Override of `website_sale`: not the variants that aren't published """
        return super()._is_add_to_cart_allowed() and (
            self.is_variant_published or self.env.user.has_group('base.group_system')
        )
