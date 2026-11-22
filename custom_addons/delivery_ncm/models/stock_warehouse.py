# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models


class StockWarehouse(models.Model):
    _inherit = 'stock.warehouse'

    ncm_pickup_branch_id = fields.Many2one(
        'ncm.branch', string="NCM Pickup Branch",
        help="Nepal Can Move branch for parcels leaving this warehouse, used for products that have "
             "no pickup branch of their own.",
    )
