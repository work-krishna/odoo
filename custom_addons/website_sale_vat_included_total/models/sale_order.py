from odoo import models


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def _total_includes_tax(self):
        """Whether the order's total includes some tax, so the shop can say "Incl. VAT" under it.

        False when no line is taxed: untaxed or 0% products, or a fiscal position mapping the
        taxes away.
        """
        self.ensure_one()
        return self.currency_id.compare_amounts(self.amount_tax, 0) > 0
