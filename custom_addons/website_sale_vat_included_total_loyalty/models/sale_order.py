from odoo import models


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def _get_summary_reward_lines(self):
        """Override of `website_sale_vat_included_total`: discounts (vouchers, promo codes, coupons,
        gift cards, eWallet) and free shipping get rows of their own. They are the lines of
        `website_order_line`, where `website_sale_loyalty` merges the lines of a discount split by
        tax. Free products stay among the items."""
        lines = super()._get_summary_reward_lines()
        if self._show_vat_included_summary():
            lines |= self.website_order_line.filtered(
                lambda line: line.reward_id.reward_type in ('discount', 'shipping')
            )
        return lines
