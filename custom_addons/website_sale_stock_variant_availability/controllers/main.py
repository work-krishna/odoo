from odoo.http import request

from odoo.addons.website_sale.controllers.main import WebsiteSale


class WebsiteSaleVariantAvailability(WebsiteSale):

    def _get_additional_shop_values(self, values, **kwargs):
        """ The ribbon of a product in the shop is the one of its first variant: of its first variant in stock instead,
        so it's not shown "Out of stock" while other variants are in stock.
        """
        res = super()._get_additional_shop_values(values, **kwargs)
        product_variants = values.get('product_variants') or {}
        available_variants = {
            product: product._get_variant_for_combination(product._get_first_available_combination())
            for product, variant in product_variants.items()
            if variant and variant._is_sold_out() and not product._is_sold_out()
        }
        if available_variants:
            res['product_variants'] = {**product_variants, **available_variants}
        return res

    def _prepare_product_values(self, product, category, **kwargs):
        """ Open the product page on a variant that's in stock rather than on an out-of-stock first variant, unless the
        URL asks for a combination.
        """
        values = super()._prepare_product_values(product, category, **kwargs)
        variant = values['product_variant']
        if not kwargs.get('attribute_values') and variant and variant._is_sold_out():
            if combination := product._get_first_available_combination():
                combination_info = product._get_combination_info(combination=combination)
                values.update(
                    combination_info=combination_info,
                    product_variant=request.env['product.product'].browse(combination_info['product_id']),
                )
        return values
