# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo.http import Controller, request, route


class NcmAddressController(Controller):

    @route('/website_sale_ncm/areas', type='jsonrpc', auth='public', website=True, readonly=True)
    def ncm_areas(self, district=None):
        """NCM delivery areas of a district, for the address form's area list."""
        return request.env['ncm.area']._ncm_frontend_areas(district)
