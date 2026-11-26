# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import _
from odoo.exceptions import UserError
from odoo.http import request

from odoo.addons.auth_signup.controllers.main import AuthSignupHome
from odoo.addons.web.controllers.home import SIGN_UP_REQUEST_PARAMS

# Let the sign-up form's mobile number through to the qcontext.
SIGN_UP_REQUEST_PARAMS.add('phone')


class AuthSignupSms(AuthSignupHome):

    def get_auth_signup_qcontext(self):
        qcontext = super().get_auth_signup_qcontext()
        qcontext['sms_signup_enabled'] = request.env.company._sms_otp_enabled('signup')
        return qcontext

    def _prepare_signup_values(self, qcontext):
        values = super()._prepare_signup_values(qcontext)
        if qcontext.get('sms_signup_enabled') and not qcontext.get('token'):
            phone = (qcontext.get('phone') or '').strip()
            if not phone:
                raise UserError(_("Enter your mobile number: we text your activation code to it."))
            values['phone'] = phone
        return values
