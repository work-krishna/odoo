# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models

from odoo.addons.sms_nestsms.tools.sms_api import nepal_mobile


class ResPartner(models.Model):
    _inherit = 'res.partner'

    sms_verified_phone = fields.Char(
        string="Phone Verified by SMS", copy=False, readonly=True, groups='base.group_user',
        help="The mobile number this contact last proved with an SMS code (98XXXXXXXX). "
             "Checkout and EMI applications don't ask again for it.",
    )

    def _sms_phone_is_verified(self, number):
        self.ensure_one()
        mobile = nepal_mobile(number)
        return bool(mobile) and self.sudo().sms_verified_phone == mobile

    def _sms_mark_phone_verified(self, number):
        mobile = nepal_mobile(number)
        if mobile:
            self.sudo().sms_verified_phone = mobile
