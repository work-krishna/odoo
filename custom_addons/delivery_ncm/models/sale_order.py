# Part of Odoo. See LICENSE file for full copyright and licensing details.

import json

from odoo import _, fields, models
from odoo.exceptions import UserError

from odoo.addons.delivery_ncm.models.ncm_request import NcmError


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    ncm_rate_breakdown = fields.Json(
        copy=False,
        help="Technical: NCM's quote (NPR) per pickup branch id, used to split the delivery charge "
             "between the order's parcels.",
    )

    def set_delivery_line(self, carrier, amount):
        res = super().set_delivery_line(carrier, amount)
        self._ncm_store_rate_breakdown(carrier)
        return res

    def _ncm_store_rate_breakdown(self, carrier):
        """Remember each parcel's quote. Right after a quote, NCM's answers are still cached."""
        for order in self:
            breakdown = False
            if carrier.delivery_type == 'ncm':
                try:
                    breakdown = {str(branch.id): charge for branch, charge in carrier._ncm_rate_groups(order)}
                except (UserError, NcmError):
                    breakdown = False
            order.ncm_rate_breakdown = breakdown

    def _ncm_pickup_branch(self, carrier=None):
        """The NCM branch chosen as pickup point, if `carrier` is the order's collect-at-branch
        method and a branch was chosen."""
        self.ensure_one()
        carrier = carrier or self.carrier_id
        location = self.pickup_location_data or {}
        if carrier != self.carrier_id or not carrier.ncm_use_locations or not location.get('id'):
            return self.env['ncm.branch']
        try:
            return self.env['ncm.branch'].sudo().browse(int(location['id'])).exists()
        except (TypeError, ValueError):
            return self.env['ncm.branch']

    def _ncm_get_dest_branch(self, partner=None, carrier=None):
        """The NCM branch this order ships to: the chosen pickup branch for collect-at-branch
        methods, otherwise the branch serving the delivery address."""
        self.ensure_one()
        branch = self._ncm_pickup_branch(carrier)
        if branch:
            return branch
        partner = partner or self.partner_shipping_id
        if partner.is_pickup_location and partner.parent_id:
            partner = partner.parent_id  # The pickup-point contact Odoo creates at confirmation.
        return partner._ncm_get_dest_branch() if partner else self.env['ncm.branch']

    def _get_pickup_locations(self, zip_code=None, country=None, **kwargs):
        """NCM branches to collect from. The selector's search box is sent as `zip_code`: a town,
        district or area name is searched; a postal code falls back to the delivery address."""
        if self.carrier_id.delivery_type != 'ncm':
            return super()._get_pickup_locations(zip_code=zip_code, country=country, **kwargs)
        self.ensure_one()
        locations = self.carrier_id._ncm_get_close_locations(self.partner_shipping_id, search=zip_code)
        if not locations:
            return {'error': _("No NCM branch found. Type a town or district, e.g. Pokhara.")}
        return {'pickup_locations': locations}

    def _set_pickup_location(self, pickup_location_data):
        """Re-price once the customer picks a branch: NCM's charge depends on the branch."""
        super()._set_pickup_location(pickup_location_data)
        carrier = self.carrier_id
        if carrier.delivery_type != 'ncm' or not self.pickup_location_data:
            return
        rate = carrier.rate_shipment(self)
        if rate.get('success'):
            location = self.pickup_location_data
            self.set_delivery_line(carrier, rate['price'])  # website_sale resets the location here...
            self.pickup_location_data = location           # ...so put it back,
            self._ncm_store_rate_breakdown(carrier)        # and quote parcels to that branch again.

    def _ncm_set_pickup_branch(self, branch):
        """Choose `branch` as this order's pickup point (used by tests and scripts)."""
        self.ensure_one()
        self._set_pickup_location(json.dumps(branch._ncm_pickup_location_values()))
