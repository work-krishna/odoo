from odoo import models


class ProductTemplateAttributeValue(models.Model):
    _inherit = 'product.template.attribute.value'

    def _filter_website_published(self):
        """ The values without those whose variants are all hidden from the website """
        return self.filtered(lambda ptav: (
            not ptav.ptav_product_variant_ids
            or any(ptav.ptav_product_variant_ids.mapped('is_variant_published'))
        ))
