from odoo import models


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    def _is_sold_out(self):
        """ Override of `website_sale_stock`: the product is sold out when none of its variants can be sold, not as soon
        as its first variant can't.
        """
        if not self.is_storable or self.allow_out_of_stock_order:
            return False
        # The free quantities of all the variants are computed at once
        return all(variant._is_sold_out() for variant in self.product_variant_ids)

    def _get_sold_out_combinations(self):
        """ The combinations of the variants that can't be sold for lack of stock

        :return: lists of `product.template.attribute.value` ids
        :rtype: list
        """
        self.ensure_one()
        if not self.is_storable or self.allow_out_of_stock_order:
            return []
        return [
            variant.product_template_attribute_value_ids.ids
            for variant in self.product_variant_ids
            if variant.product_template_attribute_value_ids and variant._is_sold_out()
        ]

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
