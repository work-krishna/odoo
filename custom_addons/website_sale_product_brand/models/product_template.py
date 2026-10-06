from odoo import api, fields, models
from odoo.fields import Domain


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    website_show_brand = fields.Boolean(
        string='Display Brand on eCommerce', default=True,
        help="Show the brand on the product's eCommerce page, and find the product with the shop's brand filter. "
             "Unticked, the product keeps its brand but it is not shown on the website. \"No Brand\" is never shown.",
    )

    def _get_website_brand(self):
        """ The brand to show on the website for this product, if any """
        self.ensure_one()
        brand = self.product_brand_id
        if not self.website_show_brand or brand == brand._get_no_brand():
            return brand.browse()
        return brand

    @api.model
    def _get_website_brand_domain(self, brands=None):
        """ The products whose brand is shown on the website, only those of `brands` if given """
        no_brand = self.env['product.brand']._get_no_brand()
        domain = Domain('website_show_brand', '=', True) & Domain('product_brand_id', '!=', no_brand.id)
        if brands is not None:
            domain &= Domain('product_brand_id', 'in', brands.ids)
        return domain

    @api.model
    def _search_get_detail(self, website, order, options):
        detail = super()._search_get_detail(website, order, options)
        if brand_ids := options.get('brand_ids'):
            detail['base_domain'].append(self._get_website_brand_domain(self.env['product.brand'].browse(brand_ids)))
        return detail

    def _to_markup_data(self, website):
        markup_data = super()._to_markup_data(website)
        if brand := self._get_website_brand():
            markup_data['brand'] = {'@type': 'Brand', 'name': brand.name}
        return markup_data
