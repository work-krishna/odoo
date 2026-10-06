from odoo import models

from odoo.addons.website.models import ir_http


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    def _is_combination_possible(self, combination, parent_combination=None, ignore_no_variant=False):
        """ Override of `product`: on the website, the combination of a variant that isn't published isn't possible """
        if not super()._is_combination_possible(combination, parent_combination, ignore_no_variant):
            return False
        if ir_http.get_request_website():
            variant = self._get_variant_for_combination(combination)
            return not variant or variant.is_variant_published
        return True

    def _get_attribute_exclusions(self, parent_combination=None, parent_name=None, combination_ids=None):
        """ Override of `product`: on the website, the variants that aren't published are grayed out like the archived
        ones.
        """
        exclusions = super()._get_attribute_exclusions(parent_combination, parent_name, combination_ids)
        if ir_http.get_request_website():
            unpublished_combinations = [
                variant.product_template_attribute_value_ids.ids
                for variant in self.product_variant_ids
                if not variant.is_variant_published and variant.product_template_attribute_value_ids
            ]
            if unpublished_combinations:
                exclusions['archived_combinations'] = list(exclusions['archived_combinations']) + unpublished_combinations
        return exclusions
