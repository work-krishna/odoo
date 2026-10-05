from odoo.addons.website_sale.controllers.delivery import Delivery


class WebsiteSaleVatIncludedTotalDelivery(Delivery):

    def _order_summary_values(self, order, **kwargs):
        """Override of `website_sale` so the "Incl. VAT" note follows a change of delivery method,
        whose line can bring tax into the total or take it out."""
        res = super()._order_summary_values(order, **kwargs)
        res['total_includes_tax'] = order._total_includes_tax()
        return res
