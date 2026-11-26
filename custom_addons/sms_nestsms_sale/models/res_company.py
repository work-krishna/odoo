# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    sms_notify_order_confirmed = fields.Boolean(string="Text on Order Confirmation", default=True)
