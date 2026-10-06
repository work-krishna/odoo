from odoo.http import request

from odoo.addons.website_sale.controllers.main import WebsiteSale


class WebsiteSaleProductBrand(WebsiteSale):

    def _get_shop_brands(self):
        """ The brands the shop is filtered on, from the `brand` query parameter: comma-separated brand slugs or ids """
        brand_ids = {request.env['ir.http']._unslug(value)[1] for value in request.httprequest.args.get('brand', '').split(',')}
        brands = request.env['product.brand'].browse(brand_id for brand_id in brand_ids if brand_id).exists()
        return brands - brands._get_no_brand()

    def _get_search_options(self, **kwargs):
        """ The products listed """
        options = super()._get_search_options(**kwargs)
        options['brand_ids'] = self._get_shop_brands().ids
        return options

    def _get_shop_domain(self, search, category, attribute_value_dict, search_in_description=True):
        """ The products the price range, categories and attributes are taken from """
        domain = super()._get_shop_domain(search, category, attribute_value_dict, search_in_description)
        if brands := self._get_shop_brands():
            domain &= request.env['product.template']._get_website_brand_domain(brands)
        return domain

    def _shop_get_query_url_kwargs(self, search, min_price, max_price, order=None, tags=None, **kwargs):
        """ Keep the brands when changing category, attributes, ... """
        query = super()._shop_get_query_url_kwargs(search, min_price, max_price, order=order, tags=tags, **kwargs)
        query['brand'] = ','.join(request.env['ir.http']._slug(brand) for brand in self._get_shop_brands())
        return query

    def _get_additional_shop_values(self, values, **kwargs):
        res = super()._get_additional_shop_values(values, **kwargs)
        brands = self._get_shop_brands()
        # The brands to choose from: those of the products found without filtering on brands
        domain = super()._get_shop_domain(values['search'], values['category'], values['attrib_values'])
        ProductTemplate = request.env['product.template']
        groups = ProductTemplate._read_group(domain & ProductTemplate._get_website_brand_domain(), ['product_brand_id'])
        available_brands = brands.union(*(brand for brand, in groups))
        res.update(
            shop_brands=brands,
            available_brands=available_brands.sorted(lambda brand: (brand.sequence, brand.name)),
        )
        return res
