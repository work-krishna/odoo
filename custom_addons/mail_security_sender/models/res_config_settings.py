from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    security_email = fields.Char(related='company_id.security_email', readonly=False)
