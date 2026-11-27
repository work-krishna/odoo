# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import models


class ResUsers(models.Model):
    _inherit = 'res.users'

    def _signup_mark_verified(self, otp=None):
        super()._signup_mark_verified(otp)
        # The texted code proves the mobile number: checkout and EMI won't ask for it again.
        if otp and otp.verified_by == 'sms' and otp.phone:
            for user in self:
                user.partner_id._sms_mark_phone_verified(otp.phone)
