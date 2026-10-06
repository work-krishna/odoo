from odoo import models


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    def _get_summary_label(self):
        """The label of the order summary's row of a line of `_get_summary_reward_lines`."""
        return self._get_line_header()
