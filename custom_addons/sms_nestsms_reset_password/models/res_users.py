# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, models

from odoo.addons.sms_nestsms.tools.sms_api import nepal_mobile


class ResUsers(models.Model):
    _inherit = 'res.users'

    @api.model
    def _reset_find_user_by_phone(self, number):
        """The one customer account whose mobile number was proven by an SMS code. A number
        nobody proved (a typo, someone else's phone) leads nowhere, and so does a number two
        accounts proved: the page then answers as for an unknown account."""
        mobile = nepal_mobile(number)
        if not mobile:
            return super()._reset_find_user_by_phone(number)
        users = self.sudo().search([('share', '=', True), ('partner_id.sms_verified_phone', '=', mobile)], limit=2)
        return users if len(users) == 1 else self.browse()

    def _reset_sms_phone(self):
        # Customers only, and only a number they proved: staff reset by email, and a reset
        # code never goes to a number typed in without proof.
        self.ensure_one()
        if not self.share:
            return super()._reset_sms_phone()
        return self.partner_id.sudo().sms_verified_phone or super()._reset_sms_phone()
