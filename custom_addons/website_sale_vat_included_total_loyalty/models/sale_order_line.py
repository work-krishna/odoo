from odoo import models


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    def _get_summary_label(self):
        """Override of `website_sale_vat_included_total`: the reward's description, which the
        program sets for customers, rather than the line's name, which prefixes it with "Free
        Shipping - " or follows it with the taxes the discount applies to."""
        return self.reward_id.description or super()._get_summary_label()
