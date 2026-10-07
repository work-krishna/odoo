from odoo import models


class Website(models.Model):
    _inherit = 'website'

    def _search_get_details(self, search_type, order, options):
        # A category matching the search shows its products instead of itself
        result = super()._search_get_details(search_type, order, options)
        if search_type in ('products', 'all'):
            result = [detail for detail in result if detail['model'] != 'product.public.category']
        return result
