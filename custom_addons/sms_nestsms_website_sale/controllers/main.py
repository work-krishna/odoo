# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import _
from odoo.exceptions import AccessError, MissingError, ValidationError
from odoo.http import request, route

from odoo.addons.sms_nestsms.tools.sms_api import nepal_mobile
from odoo.addons.website_sale.controllers.main import WebsiteSale
from odoo.addons.website_sale.controllers.payment import PaymentPortal

SESSION_KEY = 'sms_checkout_sent_to'


class WebsiteSaleSmsCheckout(WebsiteSale):

    def _check_cart_and_addresses(self, order_sudo):
        # Runs on the delivery and payment steps: confirm the number right after the address.
        if redirection := super()._check_cart_and_addresses(order_sudo):
            return redirection
        if order_sudo._sms_checkout_needs_verification():
            return request.redirect('/shop/verify_phone')

    @route('/shop/verify_phone', type='http', auth='public', website=True, sitemap=False, methods=['GET', 'POST'])
    def shop_verify_phone(self, send=None, code=None, **post):
        order_sudo = request.cart
        if redirection := super()._check_cart_and_addresses(order_sudo):
            return redirection
        if not order_sudo._sms_checkout_needs_verification():
            return request.redirect('/shop/checkout')

        partner = order_sudo.partner_id
        number = nepal_mobile(partner.phone)
        values = {
            'number': number,
            'sent_to': number and f"{number[:3]}*****{number[-2:]}",
            'edit_url': f'/shop/address?partner_id={partner.id}&address_type=billing',
        }
        Otp = request.env['sms.nestsms.otp']
        if request.httprequest.method == 'POST' and number:
            if send:
                otp, error = Otp._nestsms_send('checkout', number, order_sudo.website_id.company_id)
                if otp:
                    request.session[SESSION_KEY] = number
                    values['message'] = _("We texted you a code.")
                values['error'] = error
            elif code is not None:
                otp, error = Otp._nestsms_verify('checkout', number, code)
                if otp:
                    partner._sms_mark_phone_verified(number)
                    request.session.pop(SESSION_KEY, None)
                    return request.redirect('/shop/checkout')
                values['error'] = error
        values['code_sent'] = request.session.get(SESSION_KEY) == number
        response = request.render('sms_nestsms_website_sale.verify_phone', values)
        response.headers['Cache-Control'] = 'no-cache'
        return response


class PaymentPortalSmsCheckout(PaymentPortal):

    @route()
    def shop_payment_transaction(self, order_id, access_token, **kwargs):
        # Nobody pays around the check by calling the payment route directly.
        try:
            order_sudo = self._document_check_access('sale.order', order_id, access_token)
        except (AccessError, MissingError):
            order_sudo = None  # the parent raises the proper error
        if order_sudo and order_sudo._sms_checkout_needs_verification():
            raise ValidationError(_("Please confirm your mobile number with the SMS code first."))
        return super().shop_payment_transaction(order_id, access_token, **kwargs)
