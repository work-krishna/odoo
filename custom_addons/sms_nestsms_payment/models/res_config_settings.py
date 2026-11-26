# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    sms_notify_payment_received = fields.Boolean(related='company_id.sms_notify_payment_received', readonly=False)
