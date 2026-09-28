from odoo import fields, models

from .res_users import DEFAULT_VALIDITY, VALIDITY_PARAM


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    signup_verification_minutes = fields.Integer(
        string='Activation Code Validity', config_parameter=VALIDITY_PARAM, default=DEFAULT_VALIDITY,
        help="Minutes after which the code and link emailed to a new website sign-up expire.",
    )
