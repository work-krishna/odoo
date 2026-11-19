# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    def _get_frontend_writable_fields(self):
        """Let customers set their NCM delivery area from the address form."""
        frontend_writable_fields = super()._get_frontend_writable_fields()
        frontend_writable_fields.add('ncm_area_id')
        return frontend_writable_fields
