from lxml import etree, html

from odoo.http import request

from odoo.addons.website_sale.controllers.delivery import Delivery


class WebsiteSaleVatIncludedTotalDelivery(Delivery):

    def _order_summary_values(self, order, **kwargs):
        """Override of `website_sale` to return the summary's Order Detail table anew: a delivery
        method can change its rows (a free shipping voucher, a voucher's threshold), its amounts
        and whether the total includes tax."""
        res = super()._order_summary_values(order, **kwargs)
        if order._show_vat_included_summary():
            summary = html.fromstring(str(request.env['ir.ui.view']._render_template(
                'website_sale.total', {'website_sale_order': order, 'hide_promotions': True},
            )))
            if order_detail := summary.xpath('//table[@name="o_order_detail"]'):
                res['order_detail'] = etree.tostring(order_detail[0], encoding='unicode', method='html')
        return res
