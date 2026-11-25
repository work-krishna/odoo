# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo.http import Controller, request, route

from odoo.addons.website_sale.controllers.delivery import Delivery


class NcmAddressController(Controller):

    @route('/website_sale_ncm/areas', type='jsonrpc', auth='public', website=True, readonly=True)
    def ncm_areas(self, district=None):
        """NCM delivery areas of a district, for the address form's area list."""
        return request.env['ncm.area']._ncm_frontend_areas(district)


class NcmDelivery(Delivery):

    def _get_additional_delivery_context(self):
        """Always pass `default_pickup_locations` to the delivery method list.

        website_sale_collect's template reads it for every method that uses pickup locations, but
        only provides it when the website has a published in-store method. Without one, the list
        failed to render (KeyError) as soon as it showed "Collect at an NCM branch", e.g. when the
        customer changed the address at checkout.
        """
        res = super()._get_additional_delivery_context()
        res.setdefault('default_pickup_locations', {})
        return res
