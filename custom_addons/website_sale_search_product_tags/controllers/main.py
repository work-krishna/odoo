from odoo.fields import Domain

from odoo.addons.website_sale.controllers.main import WebsiteSale


class WebsiteSaleSearchProductTags(WebsiteSale):

    def _get_search_options(self, **post):
        options = super()._get_search_options(**post)
        # A sort chosen by the visitor applies to all the products found
        options['categoryMatchesLast'] = not post.get('order')
        return options

    def _add_search_subdomains_hook(self, search):
        # The categories and prices of the filters of the shop, from all the
        # products found
        return Domain.OR([
            super()._add_search_subdomains_hook(search) or Domain.FALSE,
            Domain('website_tag_names', 'ilike', search),
            Domain('website_category_keywords', 'ilike', search),
        ])
