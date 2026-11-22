# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    ncm_pickup_branch_id = fields.Many2one(
        'ncm.branch', string="NCM Pickup Branch",
        help="The Nepal Can Move branch this product leaves from. Leave empty to use its warehouse's "
             "branch, or the delivery method's default. An order mixing branches ships as one parcel "
             "per branch.",
    )
