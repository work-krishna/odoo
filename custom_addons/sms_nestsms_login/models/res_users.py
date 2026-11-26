# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, models
from odoo.exceptions import AccessDenied

from odoo.addons.sms_nestsms.tools.sms_api import nepal_mobile

CREDENTIAL_TYPE = 'nestsms_otp'


class ResUsers(models.Model):
    _inherit = 'res.users'

    @api.model
    def _sms_login_user(self, number):
        """The one customer (portal) account whose number was proven by an SMS code, or an
        empty recordset. Staff accounts keep their password and two-factor login; a number
        nobody proved (a typo, someone else's phone) can't open an account."""
        mobile = nepal_mobile(number)
        if not mobile:
            return self.browse()
        users = self.sudo().search([('share', '=', True), ('partner_id.sms_verified_phone', '=', mobile)], limit=2)
        return users if len(users) == 1 else self.browse()

    def _check_credentials(self, credential, env):
        if credential.get('type') != CREDENTIAL_TYPE:
            return super()._check_credentials(credential, env)
        user = self.env.user
        if self._sms_login_user(credential.get('number')) != user:
            raise AccessDenied()
        otp, error = self.env['sms.nestsms.otp']._nestsms_verify('login', credential['number'], credential.get('code'))
        if not otp:
            raise AccessDenied(error)
        # 'default': a customer who turned on two-factor authentication still gets asked for it.
        return {'uid': user.id, 'auth_method': CREDENTIAL_TYPE, 'mfa': 'default'}
