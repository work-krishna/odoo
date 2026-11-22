# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import models


class StockMove(models.Model):
    _inherit = 'stock.move'

    def _ncm_pickup_branch(self):
        """The NCM branch this move's product leaves from, when its order ships with NCM."""
        self.ensure_one()
        carrier = self.sale_line_id.order_id.carrier_id or self.picking_id.carrier_id
        if carrier.delivery_type != 'ncm':
            return self.env['ncm.branch']
        warehouse = self.warehouse_id or self.picking_type_id.warehouse_id
        return carrier._ncm_pickup_branch_for(self.product_id, warehouse)

    # One NCM order leaves from one branch: keep products of different pickup branches in
    # different transfers.

    def _key_assign_picking(self):
        return super()._key_assign_picking() + (self._ncm_pickup_branch(),)

    def _search_picking_for_assignation_domain(self):
        domain = super()._search_picking_for_assignation_domain()
        branch = self._ncm_pickup_branch()
        if branch:
            domain = [*domain, ('ncm_from_branch_id', '=', branch.id)]
        return domain

    def _get_new_picking_values(self):
        values = super()._get_new_picking_values()
        branches = self.env['ncm.branch'].union(*(move._ncm_pickup_branch() for move in self))
        if len(branches) == 1:
            values['ncm_from_branch_id'] = branches.id
        return values
