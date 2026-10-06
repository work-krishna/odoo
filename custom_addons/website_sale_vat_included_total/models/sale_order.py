from odoo import models


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def _show_vat_included_summary(self):
        """Whether the website's order summary lists Items Total, Delivery Fee and the Total, tax
        included, rather than Subtotal, Taxes and Total: the website displays prices tax
        included."""
        self.ensure_one()
        return self.website_id.show_line_subtotals_tax_selection == 'tax_included'

    def _total_includes_tax(self):
        """Whether the order's total includes some tax, so the shop can say so under it.

        False when no line is taxed: untaxed or 0% products, or a fiscal position mapping the
        taxes away.
        """
        self.ensure_one()
        return self.currency_id.compare_amounts(self.amount_tax, 0) > 0

    def _get_summary_reward_lines(self):
        """The cart lines that the order summary lists as rows of their own after the Delivery Fee,
        such as vouchers, rather than among the items. None without a discount module."""
        return self.env['sale.order.line']

    def _get_items_total(self):
        """The order summary's Items Total: the total but delivery and the rows of
        `_get_summary_reward_lines`, so that all of them, tax included, add up to the total."""
        self.ensure_one()
        rewards = sum(line._get_cart_display_price() for line in self._get_summary_reward_lines())
        return self.currency_id.round(self.amount_total - self.amount_delivery - rewards)
