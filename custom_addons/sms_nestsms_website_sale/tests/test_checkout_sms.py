# Part of Odoo. See LICENSE file for full copyright and licensing details.

import json
import re

from odoo.tests import HttpCase, tagged
from odoo.tests.common import new_test_user

from odoo.addons.sms_nestsms.tests.common import TEMPLATE_ID, approve_otp, patch_nestsms


@tagged('post_install', '-at_install')
class TestCheckoutSms(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.website = cls.env['website'].get_current_website()
        cls.website.company_id.write({
            'sms_nestsms_api_key': 'nsms_live_test',
            'sms_brand_name': 'Flagship-Store',
        })
        approve_otp(cls.website.company_id, 'checkout')
        cls.product = cls.env['product.product'].create({
            'name': 'Phone Case', 'list_price': 500.0, 'type': 'service', 'sale_ok': True, 'website_published': True,
        })
        cls.shopper = new_test_user(cls.env, login='sita@example.com', password='sita@example.com',
                                    groups='base.group_portal', name='Sita Gurung')
        cls.shopper.partner_id.write({
            'email': 'sita@example.com', 'phone': '9841234567', 'street': 'Lakeside 6', 'city': 'Pokhara',
            'zip': '33700', 'country_id': cls.env.ref('base.np').id,
        })

    def setUp(self):
        super().setUp()
        self.nestsms = patch_nestsms(self)
        self.authenticate('sita@example.com', 'sita@example.com')
        self.make_jsonrpc_request('/shop/cart/add', {
            'product_template_id': self.product.product_tmpl_id.id, 'product_id': self.product.id, 'quantity': 1,
        })
        self.order = self.env['sale.order'].search([('partner_id', '=', self.shopper.partner_id.id)], limit=1)

    def _csrf(self):
        return re.search(r'name="csrf_token" value="([^"]+)"', self.url_open('/shop/verify_phone').text).group(1)

    def _post(self, **data):
        return self.url_open('/shop/verify_phone', data={'csrf_token': self._csrf(), **data})

    def test_checkout_asks_for_the_code(self):
        response = self.url_open('/shop/checkout')
        self.assertTrue(response.url.endswith('/shop/verify_phone'))
        self.assertIn('984*****67', response.text)

        self._post(send='1')
        [call] = self.nestsms.calls
        self.assertEqual(call['payload']['template_id'], TEMPLATE_ID)
        code = call['payload']['variables']['otp']

        self.assertIn('4 tries left', self._post(code='000000' if code != '000000' else '111111').text)
        response = self._post(code=code)
        self.assertNotIn('verify_phone', response.url)
        self.assertEqual(self.shopper.partner_id.sms_verified_phone, '9841234567')
        self.assertFalse(self.url_open('/shop/checkout').url.endswith('/shop/verify_phone'))

    def test_payment_route_is_guarded(self):
        response = self.url_open(
            f'/shop/payment/transaction/{self.order.id}',
            data=json.dumps({'jsonrpc': '2.0', 'method': 'call', 'id': 1, 'params': {
                'access_token': self.order._portal_ensure_token(),
                'payment_method_id': 1, 'provider_id': 1, 'token_id': None, 'amount': None,
                'flow': 'redirect', 'tokenization_requested': False, 'landing_route': '/shop/payment/validate',
            }}),
            headers={'Content-Type': 'application/json'},
        )
        self.assertIn('confirm your mobile number', response.json()['error']['data']['message'])

    def test_number_proven_before_is_not_asked_again(self):
        self.shopper.partner_id.sms_verified_phone = '9841234567'
        self.assertFalse(self.url_open('/shop/checkout').url.endswith('/shop/verify_phone'))

    def test_changed_number_is_asked_again(self):
        self.shopper.partner_id.write({'sms_verified_phone': '9841234567', 'phone': '9801234567'})
        self.assertTrue(self.url_open('/shop/checkout').url.endswith('/shop/verify_phone'))

    def test_no_nepali_mobile(self):
        self.shopper.partner_id.phone = '+1 555 123 4567'
        response = self.url_open('/shop/verify_phone')
        self.assertIn('we need a Nepali mobile number', response.text)
        self.assertNotIn('name="send"', response.text)

    def test_switched_off(self):
        self.website.company_id.sms_otp_checkout = False
        self.assertFalse(self.url_open('/shop/checkout').url.endswith('/shop/verify_phone'))
