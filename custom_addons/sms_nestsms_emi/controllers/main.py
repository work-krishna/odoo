# Part of Odoo. See LICENSE file for full copyright and licensing details.

from werkzeug.urls import url_encode

from odoo import _, http
from odoo.http import request

from odoo.addons.emi_storefront.controllers.apply import EmiApply
from odoo.addons.sms_nestsms.tools.sms_api import nepal_mobile

VERIFY_URL = '/my/emi/verify-phone'
SESSION_KEY = 'sms_emi_sent_to'


def _local_path(url, default='/my'):
    """Only redirect within this site."""
    return url if url and url.startswith('/') and not url.startswith('//') else default


class EmiApplySms(EmiApply):

    def _sms_emi_required(self):
        return request.env.company._sms_otp_enabled('emi')

    def _sms_emi_verify_url(self, phone_slug):
        return f"{VERIFY_URL}?{url_encode({'redirect': f'/phones/{phone_slug}/apply'})}"

    def _form_context(self, phone, values=None, error=None):
        context = super()._form_context(phone, values=values, error=error)
        if self._sms_emi_required():
            context['values']['phone'] = request.env.user.partner_id.sudo().sms_verified_phone
            context['sms_phone_locked'] = True
            context['sms_verify_url'] = self._sms_emi_verify_url(request.env['ir.http']._slug(phone))
        return context

    @http.route()
    def apply_form(self, phone_slug, **kwargs):
        if self._sms_emi_required() and not request.env.user.partner_id.sudo().sms_verified_phone:
            return request.redirect(self._sms_emi_verify_url(phone_slug))
        return super().apply_form(phone_slug, **kwargs)

    @http.route()
    def apply_submit(self, phone_slug, **post):
        if self._sms_emi_required():
            verified = request.env.user.partner_id.sudo().sms_verified_phone
            if not verified:
                return request.redirect(self._sms_emi_verify_url(phone_slug))
            # The application carries the number proven by SMS, whatever the form sent.
            post['phone'] = verified
        return super().apply_submit(phone_slug, **post)

    @http.route(VERIFY_URL, type='http', auth='user', website=True, sitemap=False, methods=['GET', 'POST'])
    def emi_verify_phone(self, phone=None, send=None, code=None, redirect=None, **kw):
        redirect = _local_path(redirect)
        if not self._sms_emi_required():
            return request.redirect(redirect)
        partner = request.env.user.partner_id
        number = request.session.get(SESSION_KEY)
        values = {'redirect': redirect}
        if request.httprequest.method == 'POST':
            if send:
                mobile = nepal_mobile(phone)
                if not mobile:
                    values['error'] = _("Enter a Nepali mobile number (98XXXXXXXX).")
                else:
                    otp, error = request.env['sms.nestsms.otp']._nestsms_send('emi', mobile, request.env.company)
                    if otp:
                        request.session[SESSION_KEY] = number = mobile
                        values['message'] = _("We texted you a code.")
                    values['error'] = error
            elif code is not None and number:
                otp, error = request.env['sms.nestsms.otp']._nestsms_verify('emi', number, code)
                if otp:
                    partner._sms_mark_phone_verified(number)
                    request.session.pop(SESSION_KEY, None)
                    return request.redirect(redirect)
                values['error'] = error
        values.update(
            number=number,
            sent_to=number and f"{number[:3]}*****{number[-2:]}",
            default_phone=number or nepal_mobile(partner.phone) or '',
        )
        response = request.render('sms_nestsms_emi.verify_phone', values)
        response.headers['Cache-Control'] = 'no-cache'
        return response
