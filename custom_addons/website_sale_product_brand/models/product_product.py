from odoo import models


class ProductProduct(models.Model):
    _inherit = 'product.product'

    def _to_markup_data(self, website):
        markup_data = super()._to_markup_data(website)
        if brand := self.product_tmpl_id._get_website_brand():
            markup_data['brand'] = {'@type': 'Brand', 'name': brand.name}
        return markup_data
