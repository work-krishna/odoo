# Part of Odoo. See LICENSE file for full copyright and licensing details.

import json
import re

from odoo.exceptions import ValidationError
from odoo.tests import HttpCase, tagged
from odoo.tests.common import new_test_user

from odoo.addons.sms_nestsms.tests.common import TEMPLATE_ID, approve_otp, patch_nestsms

BUYER = '9841234567'
RECIPIENT = '9801112222'


@tagged('post_install', '-at_install')
class TestCheckoutSms(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.website = cls.env['website'].get_current_website()
        cls.company = cls.website.company_id
        cls.company.write({
            'sms_nestsms_api_key': 'nsms_live_test',
            'sms_brand_name': 'Flagship-Store',
        })
        approve_otp(cls.company, 'checkout')
        cls.product = cls.env['product.product'].create({
            'name': 'Phone Case', 'list_price': 500.0, 'type': 'service', 'sale_ok': True, 'website_published': True,
        })
        cls.shopper = new_test_user(cls.env, login='sita@example.com', password='sita@example.com',
                                    groups='base.group_portal', name='Sita Gurung')
        cls.buyer = cls.shopper.partner_id
        cls.buyer.write({
            'email': 'sita@example.com', 'phone': BUYER, 'street': 'Lakeside 6', 'city': 'Pokhara',
            'zip': '33700', 'country_id': cls.env.ref('base.np').id,
        })

    def setUp(self):
        super().setUp()
        self.nestsms = patch_nestsms(self)
        self.authenticate('sita@example.com', 'sita@example.com')
        self.make_jsonrpc_request('/shop/cart/add', {
            'product_template_id': self.product.product_tmpl_id.id, 'product_id': self.product.id, 'quantity': 1,
        })
        self.order = self.env['sale.order'].search([('partner_id', '=', self.buyer.id)], limit=1)

    def _csrf(self, url='/shop/verify_phone'):
        return re.search(r'name="csrf_token" value="([^"]+)"', self.url_open(url).text).group(1)

    def _post(self, **data):
        return self.url_open('/shop/verify_phone', data={'csrf_token': self._csrf(), **data})

    def _held_at_checkout(self):
        return self.url_open('/shop/checkout').url.endswith('/shop/verify_phone')

    def _text_and_confirm(self, number):
        self._post(send='1', mobile=number)
        call = self.nestsms.calls[-1]
        self.assertEqual(call['payload']['to'], number)
        self.assertEqual(call['payload']['template_id'], TEMPLATE_ID)
        return self._post(code=call['payload']['variables']['otp'])

    def _jsonrpc(self, url, params):
        response = self.url_open(url, data=json.dumps({'jsonrpc': '2.0', 'method': 'call', 'id': 1, 'params': params}),
                                 headers={'Content-Type': 'application/json'})
        return response.json()

    def _pay_params(self):
        return {
            'access_token': self.order._portal_ensure_token(),
            'payment_method_id': 1, 'provider_id': 1, 'token_id': None, 'amount': None,
            'flow': 'redirect', 'tokenization_requested': False, 'landing_route': '/shop/payment/validate',
        }

    def test_checkout_asks_for_the_buyers_own_number(self):
        response = self.url_open('/shop/checkout')
        self.assertTrue(response.url.endswith('/shop/verify_phone'))
        self.assertIn(f'value="{BUYER}"', response.text, "Prefilled with the buyer's contact number.")
        self.assertIn('Buying for someone else?', response.text)

        self._post(send='1', mobile=BUYER)
        [call] = self.nestsms.calls
        code = call['payload']['variables']['otp']
        page = self._post(code='000000' if code != '000000' else '111111').text
        self.assertIn('4 tries left', page)
        self.assertIn(f'Code we texted to <strong>{BUYER}</strong>', page)

        response = self._post(code=code)
        self.assertNotIn('verify_phone', response.url)
        self.assertEqual(self.buyer.sms_verified_phone, BUYER)
        self.assertEqual(self.order.sms_verified_phone, BUYER, "Shown on the order for the delivery call.")
        self.assertFalse(self._held_at_checkout())

    def test_buyer_proves_their_number_while_the_address_has_the_recipients(self):
        self.buyer.phone = RECIPIENT  # the first address form edits the buyer's own contact
        self.assertIn(f'value="{RECIPIENT}"', self.url_open('/shop/verify_phone').text)
        self.assertNotIn('verify_phone', self._text_and_confirm(BUYER).url)
        self.assertEqual(self.buyer.sms_verified_phone, BUYER)
        self.assertEqual(self.buyer.phone, RECIPIENT, "The address keeps the recipient's number.")
        self.assertFalse(self._held_at_checkout())

    def test_another_delivery_number_needs_no_code(self):
        self.buyer.sms_verified_phone = BUYER
        delivery = self.env['res.partner'].create({
            'name': 'Hari Gurung', 'type': 'delivery', 'parent_id': self.buyer.id, 'phone': RECIPIENT,
            'street': 'Baneshwor 10', 'city': 'Kathmandu', 'zip': '44600', 'country_id': self.env.ref('base.np').id,
        })
        self.order.partner_shipping_id = delivery
        self.assertFalse(self._held_at_checkout())

    def test_a_proven_number_counts_after_the_contact_number_changes(self):
        self.buyer.write({'sms_verified_phone': BUYER, 'phone': RECIPIENT})
        self.assertFalse(self._held_at_checkout())
        self.assertNotIn('verify_phone', self.url_open('/shop/verify_phone').url)

    def test_not_a_nepali_mobile(self):
        page = self._post(send='1', mobile='+1 555 123 4567').text
        self.assertIn('Enter your Nepali mobile number', page)
        self.assertFalse(self.nestsms.calls)
        self.assertTrue(self._held_at_checkout())

    def test_a_code_without_one_sent_does_nothing(self):
        self.assertTrue(self._post(code='123456').url.endswith('/shop/verify_phone'))
        self.assertFalse(self.buyer.sms_verified_phone)

    def test_held_while_codes_cannot_be_sent(self):
        self.company._sms_otp_set_approved('checkout', False)  # e.g. NestSMS rejected the template
        self.assertTrue(self._held_at_checkout(), "Strict: no silent skipping.")
        self.assertIn("We can't text confirmation codes at the moment", self.url_open('/shop/verify_phone').text)
        page = self.url_open('/shop/verify_phone', data={  # the held page has no form to take a token from
            'csrf_token': self._csrf('/my/account'), 'send': '1', 'mobile': BUYER,
        }).text
        self.assertIn("We can't text confirmation codes at the moment", page)
        self.assertNotIn('name="mobile"', page)
        self.assertFalse(self.nestsms.calls)
        reply = self._jsonrpc(f'/shop/payment/transaction/{self.order.id}', self._pay_params())
        self.assertIn('confirm your mobile number', reply['error']['data']['message'])

    def test_payment_routes_are_guarded(self):
        reply = self._jsonrpc(f'/shop/payment/transaction/{self.order.id}', self._pay_params())
        self.assertIn('confirm your mobile number', reply['error']['data']['message'])
        # A cart's access token also opens the quotation payment route.
        reply = self._jsonrpc(f'/my/orders/{self.order.id}/transaction', self._pay_params())
        self.assertIn('confirm your mobile number', reply['error']['data']['message'])
        # Free orders are confirmed without a payment, through the same cart check.
        with self.assertRaises(ValidationError):
            self.order._check_cart_is_ready_to_be_paid()

    def test_switched_off(self):
        self.company.sms_otp_checkout = False
        self.assertFalse(self._held_at_checkout())
        self.assertFalse(self.order._sms_checkout_needs_verification())

    def test_orders_outside_the_website_are_not_concerned(self):
        quotation = self.env['sale.order'].create({'partner_id': self.buyer.id})
        self.assertFalse(quotation._sms_checkout_needs_verification())
