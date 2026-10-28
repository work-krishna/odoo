from odoo import api, models
from odoo.http import request


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    def _is_sold_out(self):
        """ Override of `website_sale_stock`: the product is sold out when none of its variants can be sold, not as soon
        as its first variant can't.
        """
        if not self.product_variant_ids:
            return super()._is_sold_out()
        # The free quantities of all the variants are computed at once
        return all(variant._is_sold_out() for variant in self.product_variant_ids)

    def _get_sold_out_combinations(self):
        """ The combinations of the variants that can't be sold for lack of stock

        :return: lists of `product.template.attribute.value` ids
        :rtype: list
        """
        self.ensure_one()
        return [
            variant.product_template_attribute_value_ids.ids
            for variant in self.product_variant_ids
            if variant.product_template_attribute_value_ids and variant._is_sold_out()
        ]

    def _get_additionnal_combination_info(self, product_or_template, quantity, uom, date, website):
        """ Override of `website_sale_stock`: the product page of a variant marked out of stock shows Odoo's "Out of
        Stock", without Add to Cart, even if its inventory isn't tracked.
        """
        res = super()._get_additionnal_combination_info(product_or_template, quantity, uom, date, website)
        if not (
            self.env.context.get('website_sale_stock_get_quantity')
            and product_or_template.is_product_variant
            and product_or_template.is_variant_out_of_stock
        ):
            return res
        product_sudo = product_or_template.sudo()
        res.update({
            'is_storable': True,
            'allow_out_of_stock_order': False,
            'available_threshold': product_sudo.available_threshold,
            'free_qty': 0,
            'cart_qty': 0,
            'uom_name': uom.name,
            'uom_rounding': uom.rounding,
            'show_availability': False,
            'out_of_stock_message': product_sudo.out_of_stock_message,
        })
        # Set by `website_sale_stock` for the products whose inventory is tracked
        res.setdefault('has_stock_notification', (
            product_sudo._has_stock_notification(self.env.user.partner_id)
            or bool(request and product_sudo.id in request.session.get('product_with_stock_notification_enabled', []))
        ))
        res.setdefault('stock_notification_email', request and request.session.get('stock_notification_email', ''))
        return res

    @api.model
    def _get_additional_configurator_data(
        self, product_or_template, date, currency, pricelist, *, uom=None, **kwargs
    ):
        """ Override of `website_sale_stock`: the window to choose the options of a product doesn't sell the variants
        marked out of stock either.
        """
        data = super()._get_additional_configurator_data(
            product_or_template, date, currency, pricelist, uom=uom, **kwargs
        )
        if product_or_template.is_product_variant and product_or_template.is_variant_out_of_stock:
            data['free_qty'] = 0
        return data

    def _add_sold_out_combinations(self, attribute_exclusions):
        """ Have the product page's variant selector gray out the out-of-stock variants like the archived ones, by
        adding them to the archived combinations.

        :param dict attribute_exclusions: as returned by `_get_attribute_exclusions`
        :rtype: dict
        """
        sold_out_combinations = self._get_sold_out_combinations()
        if not sold_out_combinations:
            return attribute_exclusions
        return {
            **attribute_exclusions,
            'archived_combinations': list(attribute_exclusions['archived_combinations']) + sold_out_combinations,
        }

    def _get_first_available_combination(self):
        """ The first possible combination, following the sequence of attributes and values, whose variant isn't sold
        out. Empty if they all are.

        :rtype: product.template.attribute.value recordset
        """
        self.ensure_one()
        available_variants = self.product_variant_ids.filtered(lambda variant: not variant._is_sold_out())
        positions = {
            ptav.id: (line_index, value_index)
            for line_index, ptal in enumerate(self.valid_product_template_attribute_line_ids)
            for value_index, ptav in enumerate(ptal.product_template_value_ids._only_active())
        }

        def attribute_order(variant):
            return sorted(positions.get(ptav.id, (len(positions), 0)) for ptav in variant.product_template_attribute_value_ids)

        for variant in available_variants.sorted(attribute_order):
            # Completed with the values of the attributes that don't create variants
            if combination := self._get_first_possible_combination(necessary_values=variant.product_template_attribute_value_ids):
                return combination
        return self.env['product.template.attribute.value']
