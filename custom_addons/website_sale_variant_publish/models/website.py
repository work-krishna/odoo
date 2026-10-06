from odoo import models
from odoo.fields import Domain


class Website(models.Model):
    _inherit = 'website'

    def sale_product_domain(self):
        """ Override of `website_sale`: not the products whose variants are all hidden from the website """
        domain = super().sale_product_domain()
        if self.env.user._is_internal():
            return domain
        return domain & (
            Domain('product_variant_ids', 'any', [('is_variant_published', '=', True)])
            | Domain('product_variant_ids', '=', False)
        )
