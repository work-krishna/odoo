from odoo.http import request

from odoo.addons.website_sale.controllers.main import WebsiteSale


class WebsiteSaleVariantPublish(WebsiteSale):

    def _prepare_product_values(self, product, category, **kwargs):
        """ A link to a variant that isn't published opens the product page on its first published variant """
        values = super()._prepare_product_values(product, category, **kwargs)
        variant = values['product_variant']
        if variant and not variant.is_variant_published:
            combination_info = product._get_combination_info()
            values.update(
                combination_info=combination_info,
                product_variant=request.env['product.product'].browse(combination_info['product_id']),
            )
        return values
