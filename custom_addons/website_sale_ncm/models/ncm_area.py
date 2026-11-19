# Part of Odoo. See LICENSE file for full copyright and licensing details.

from collections import Counter

from odoo import api, models


class NcmArea(models.Model):
    _inherit = 'ncm.area'

    @api.model
    def _ncm_frontend_districts(self):
        """Districts NCM serves, for the address form's district list."""
        groups = self.sudo()._read_group([('branch_id.active', '=', True)], ['district'])
        return sorted(district for (district,) in groups if district)

    @api.model
    def _ncm_frontend_areas(self, district):
        """Areas of `district` as {'id', 'label'} for the address form. An area name listed under
        several branches of the district gets the branch name, so customers can tell them apart."""
        if not district:
            return []
        areas = self.sudo().search(
            [('district', '=', str(district).strip().upper()), ('branch_id.active', '=', True)],
            order='name, branch_id',
        )
        counts = Counter(areas.mapped('name'))
        return [
            {
                'id': area.id,
                'label': (
                    f"{area.name.title()} ({area.branch_id.name.title()} branch)"
                    if counts[area.name] > 1 else area.name.title()
                ),
            }
            for area in areas
        ]
