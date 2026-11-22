# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import models


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def _get_delivery_methods(self):
        """Hide NCM methods that cannot ship this cart (no API token, or a product without a pickup
        branch) instead of showing shoppers a setup error."""
        methods = super()._get_delivery_methods()
        return methods.filtered(lambda method: method._ncm_is_ready_for_order(self))
