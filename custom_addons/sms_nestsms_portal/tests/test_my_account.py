# Part of Odoo. See LICENSE file for full copyright and licensing details.

import re

from odoo.tests import HttpCase, tagged
from odoo.tests.common import new_test_user

from odoo.addons.sms_nestsms.tests.common import TEMPLATE_ID, approve_otp, patch_nestsms

MOBILE = '9841234567'


@tagged('post_install', '-at_install')
class TestMyAccountVerification(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.company.write({'sms_nestsms_api_key': 'nsms_live_test', 'sms_brand_name': 'Flagship-Store'})
        approve_otp(cls.env.company, 'verify_phone')
        cls.user = new_test_user(cls.env, login='sita@example.com', password='sita@example.com',
                                 groups='base.group_portal', email='sita@example.com', name='Sita Gurung')
        cls.partner = cls.user.partner_id
        cls.partner.write({'phone': MOBILE, 'street': 'Lakeside 6', 'city': 'Pokhara',
                           'country_id': cls.env.ref('base.np').id})

    def setUp(self):
        super().setUp()
        self.nestsms = patch_nestsms(self)
        self.authenticate('sita@example.com', 'sita@example.com')

    def _block(self, page, field):
        match = re.search(rf'<div[^>]*id="o_{field}_verification".*?</div>', page, re.S)
        return match and match.group(0) or ''

    def _account(self):
        return self.url_open('/my/account').text

    def _csrf(self):
        return re.search(r'name="csrf_token" value="([^"]+)"', self.url_open('/my/verify-phone').text).group(1)

    def _post(self, **data):
        return self.url_open('/my/verify-phone', data={'csrf_token': self._csrf(), **data})

    def test_status_and_verify_buttons(self):
        page = self._account()
        email = self._block(page, 'email')
        self.assertIn('Verified', email)
        self.assertNotIn('Not verified', email)
        phone = self._block(page, 'phone')
        self.assertIn('Not verified', phone)
        self.assertIn('href="/my/verify-phone"', phone)

    def test_unconfirmed_email_has_a_verify_button(self):
        self.user.signup_email_verified = False
        email = self._block(self._account(), 'email')
        self.assertIn('Not verified', email)
        self.assertIn('href="/my/verify-email?redirect=/my/account"', email)

    def test_changed_email_is_unconfirmed_until_verified(self):
        self.partner.email = 'sita.gurung@example.com'
        email = self._block(self._account(), 'email')
        self.assertIn('Not verified', email)
        self.assertIn('/my/verify-email', email)

    def test_verify_the_mobile_number(self):
        page = self.url_open('/my/verify-phone').text
        self.assertIn(MOBILE, page)
        self.assertIn('Text me a code', page)
        self._post(send='1')
        [call] = self.nestsms.calls
        self.assertEqual(call['payload']['to'], MOBILE)
        self.assertEqual(call['payload']['template_id'], TEMPLATE_ID)
        code = call['payload']['variables']['otp']

        self.assertIn('4 tries left', self._post(code='000000' if code != '000000' else '111111').text)
        self.assertIn('Mobile number verified', self._post(code=code).text)
        self.assertEqual(self.partner.sms_verified_phone, MOBILE)
        otp = self.env['auth.otp'].sudo().search([('purpose', '=', 'verify_phone'), ('user_id', '=', self.user.id)])
        self.assertEqual(otp.verified_by, 'sms')

        phone = self._block(self._account(), 'phone')
        self.assertIn('Verified', phone)
        self.assertNotIn('Not verified', phone)
        self.assertTrue(self.url_open('/my/verify-phone').url.endswith('/my/account'))

    def test_code_for_an_old_number_is_refused(self):
        self._post(send='1')
        code = self.nestsms.calls[0]['payload']['variables']['otp']
        self.partner.phone = '9801112222'
        self.assertIn('changed since', self._post(code=code).text)
        self.assertFalse(self.partner.sms_verified_phone)

    def test_another_verified_number_is_named(self):
        self.partner.write({'sms_verified_phone': '9801112222'})
        phone = self._block(self._account(), 'phone')
        self.assertIn('Not verified', phone)
        self.assertIn('Your verified number is 9801112222', phone)

    def test_number_outside_nepal(self):
        self.partner.phone = '+1 555 123 4567'
        phone = self._block(self._account(), 'phone')
        self.assertIn('Only Nepali mobile numbers', phone)
        self.assertNotIn('/my/verify-phone', phone)
        self.assertTrue(self.url_open('/my/verify-phone').url.endswith('/my/account'))

    def test_no_verify_button_while_sms_codes_are_off(self):
        self.env.company._sms_otp_set_approved('verify_phone', False)
        phone = self._block(self._account(), 'phone')
        self.assertIn('Not verified', phone)
        self.assertNotIn('/my/verify-phone', phone)
        self.assertIn("can't text verification codes", self.url_open('/my/verify-phone').text)

    def test_other_address_forms_show_nothing(self):
        child = self.env['res.partner'].create({
            'name': 'Hari Gurung', 'type': 'delivery', 'parent_id': self.partner.id, 'phone': '9801112222',
            'email': 'hari@example.com', 'street': 'Baneshwor', 'city': 'Kathmandu', 'country_id': self.env.ref('base.np').id,
        })
        page = self.url_open(f'/my/address?partner_id={child.id}').text
        self.assertIn('o_phone', page)
        self.assertNotIn('o_contact_verification', page)
