from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    website_show_brand = fields.Boolean(
        string='Display Brand on eCommerce', default=True,
        help="Show the brand on the product's eCommerce page. Unticked, the product keeps its brand but it is not "
             "shown on the website. \"No Brand\" is never shown.",
    )

    def _get_website_brand(self):
        """ The brand to show on the website for this product, if any """
        self.ensure_one()
        brand = self.product_brand_id
        if not self.website_show_brand or brand == brand._get_no_brand():
            return brand.browse()
        return brand

    def _to_markup_data(self, website):
        markup_data = super()._to_markup_data(website)
        if brand := self._get_website_brand():
            markup_data['brand'] = {'@type': 'Brand', 'name': brand.name}
        return markup_data
