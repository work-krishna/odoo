# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models


class DeliveryCarrier(models.Model):
    _inherit = 'delivery.carrier'

    ncm_notify_customer_sms = fields.Boolean(
        string="Text Customers",
        help="Text the customer through NestSMS when NCM sends the parcel out for delivery, and when it is delivered.",
    )
