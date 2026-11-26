# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models


class AuthSignupVerification(models.Model):
    _inherit = 'auth.signup.verification'

    channel = fields.Selection(selection_add=[('sms', "SMS")], ondelete={'sms': 'set default'})
