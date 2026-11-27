# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging

from odoo import _
from odoo.exceptions import AccessError, MissingError, ValidationError
from odoo.http import request, route

from odoo.addons.sale.controllers.portal import PaymentPortal as SalePaymentPortal
from odoo.addons.sms_nestsms.tools.sms_api import nepal_mobile
from odoo.addons.website_sale.controllers.main import WebsiteSale

_logger = logging.getLogger(__name__)

SESSION_KEY = 'sms_checkout_sent_to'


class WebsiteSaleSmsCheckout(WebsiteSale):

    def _check_cart_and_addresses(self, order_sudo):
        # Runs on the delivery and payment steps: confirm the number right after the address.
        if redirection := super()._check_cart_and_addresses(order_sudo):
            return redirection
        if order_sudo._sms_checkout_needs_verification():
            return request.redirect('/shop/verify_phone')

    @route('/shop/verify_phone', type='http', auth='public', website=True, sitemap=False, methods=['GET', 'POST'])
    def shop_verify_phone(self, mobile=None, send=None, code=None, **post):
        """The buyer proves their own mobile number. It is typed here, apart from the addresses,
        so a delivery address can carry someone else's number without that person getting
        the code."""
        order_sudo = request.cart
        if redirection := super()._check_cart_and_addresses(order_sudo):
            return redirection
        if not order_sudo._sms_checkout_needs_verification():
            return request.redirect('/shop/checkout')

        partner = order_sudo.partner_id
        sent_to = request.session.get(SESSION_KEY)
        values = {
            'available': order_sudo._sms_checkout_codes_available(),
            'mobile': sent_to or nepal_mobile(partner.phone) or '',
        }
        if not values['available']:
            _logger.warning("Checkout of %s held: the checkout SMS template isn't approved.", order_sudo.name)
        elif request.httprequest.method == 'POST':
            Otp = request.env['auth.otp']
            if send:
                number = nepal_mobile(mobile)
                values['mobile'] = number or (mobile or '').strip()
                if not number:
                    values['error'] = _("Enter your Nepali mobile number: 10 digits, like 98XXXXXXXX.")
                else:
                    result = Otp._otp_issue('checkout', phone=number, company=order_sudo._sms_checkout_company())
                    if result['otp']:
                        request.session[SESSION_KEY] = sent_to = number
                        values['message'] = _("We texted you a code.")
                    values['error'] = result['error']
            elif code is not None and sent_to:
                otp, error = Otp._otp_verify('checkout', code, phone=sent_to)
                if otp:
                    partner._sms_mark_phone_verified(sent_to)
                    if not partner.phone:
                        partner.sudo().phone = sent_to
                    request.session.pop(SESSION_KEY, None)
                    return request.redirect('/shop/checkout')
                values['error'] = error
        values['sent_to'] = sent_to
        response = request.render('sms_nestsms_website_sale.verify_phone', values)
        response.headers['Cache-Control'] = 'no-cache'
        return response


class PaymentPortalSmsCheckout(SalePaymentPortal):

    @route()
    def portal_order_transaction(self, order_id, access_token, **kwargs):
        # A cart's access token also opens the quotation payment route: nobody pays around
        # checkout there. (The shop's own payment route checks the cart itself.)
        try:
            order_sudo = self._document_check_access('sale.order', order_id, access_token)
        except (AccessError, MissingError):
            order_sudo = None  # the parent raises the proper error
        if order_sudo and order_sudo.state == 'draft' and order_sudo._sms_checkout_needs_verification():
            raise ValidationError(_("Please confirm your mobile number with the SMS code first."))
        return super().portal_order_transaction(order_id, access_token, **kwargs)
