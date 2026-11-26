# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    # New companies start on our wording too (the core default is a plain function, so
    # overriding the method alone wouldn't change it).
    stock_sms_confirmation_template_id = fields.Many2one(
        default=lambda self: self.env.ref('sms_nestsms_stock.sms_template_shipped', raise_if_not_found=False),
    )
