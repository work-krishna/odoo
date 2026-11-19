# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    ncm_area_id = fields.Many2one(
        'ncm.area', string="NCM Delivery Area", index='btree_not_null',
        help="Nepal Can Move coverage area of this address. It decides which NCM branch delivers here; "
             "when empty, the branch is guessed from the city.",
    )

    def _ncm_get_dest_branch(self):
        """The NCM branch delivering to this address (empty when it cannot be told)."""
        self.ensure_one()
        branch = self.ncm_area_id.branch_id
        if branch.active:
            return branch
        return self.env['ncm.area']._ncm_match_partner(self)
