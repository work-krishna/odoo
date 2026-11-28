# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import _, fields, http
from odoo.http import request

from odoo.addons.portal.controllers.portal import CustomerPortal
from odoo.addons.sms_nestsms.tools.sms_api import nepal_mobile

PURPOSE = 'verify_phone'
ACCOUNT_URL = '/my/account'


class ContactVerification(CustomerPortal):

    def _prepare_my_account_rendering_values(self, *args, **kwargs):
        values = super()._prepare_my_account_rendering_values(*args, **kwargs)
        user = request.env.user
        partner = user.partner_id.sudo()
        mobile = nepal_mobile(partner.phone)
        values['contact_verification'] = {
            'email_verified': bool(user.sudo().signup_email_verified),
            'email_can_verify': user._signup_email_unverified(),
            'phone_verified': partner._sms_phone_is_verified(partner.phone),
            'phone_is_mobile': bool(mobile),
            'phone_can_verify': bool(mobile) and request.env['auth.otp'].sudo()._otp_sms_available(PURPOSE, request.env.company),
            'verified_phone': partner.sms_verified_phone,
        }
        return values

    @http.route('/my/verify-phone', type='http', auth='user', website=True, sitemap=False, methods=['GET', 'POST'])
    def verify_phone(self, send=None, code=None, **kwargs):
        """Prove the mobile number on the account with an SMS code."""
        user = request.env.user
        partner = user.partner_id.sudo()
        number = nepal_mobile(partner.phone)
        if not number or partner._sms_phone_is_verified(number):
            return request.redirect(ACCOUNT_URL)
        Otp = request.env['auth.otp'].sudo()
        values = {'number': number, 'available': Otp._otp_sms_available(PURPOSE, request.env.company)}
        if request.httprequest.method == 'POST' and values['available']:
            if send:
                result = Otp._otp_issue(PURPOSE, user=user, phone=number, company=request.env.company)
                if result['otp']:
                    values['message'] = _("We texted you a code.")
                values['error'] = result['error']
            elif code is not None:
                otp, error = Otp._otp_verify(PURPOSE, code, user=user)
                if otp and otp.phone != number:
                    otp, error = False, _("Your mobile number changed since we sent this code. Ask for a new one.")
                if otp:
                    partner._sms_mark_phone_verified(number)
                    return request.render('sms_nestsms_portal.verify_phone_done', {'number': number})
                values['error'] = error
        pending = Otp._otp_live(PURPOSE, user=user)
        values['code_sent'] = bool(pending) and pending.phone == number and pending.expires_at > fields.Datetime.now()
        response = request.render('sms_nestsms_portal.verify_phone', values)
        response.headers['Cache-Control'] = 'no-cache'
        return response
