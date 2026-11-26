# Part of Odoo. See LICENSE file for full copyright and licensing details.

import re
from unittest.mock import patch

from odoo.tests import HttpCase, tagged

from odoo.addons.sms_nestsms.tests.common import TEMPLATE_ID, approve_otp, fake_response, patch_nestsms

MODULE = 'odoo.addons.auth_signup_email_otp.models.res_users'
PASSWORD = 'Str0ng-Signup-Pass'


@tagged('post_install', '-at_install')
class TestSignupSms(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env['ir.config_parameter'].sudo().set_param('auth_signup.invitation_scope', 'b2c')
        if 'website' in cls.env:
            cls.env['website'].search([]).auth_signup_uninvited = 'b2c'
        cls.env.company.write({
            'sms_nestsms_api_key': 'nsms_live_test',
            'sms_brand_name': 'Flagship-Store',
            'country_id': cls.env.ref('base.np').id,
        })
        approve_otp(cls.env.company, 'signup')

    def setUp(self):
        super().setUp()
        self.nestsms = patch_nestsms(self)

    def _csrf(self, url='/web/login'):
        return re.search(r'name="csrf_token" value="([^"]+)"', self.url_open(url).text).group(1)

    def _signup(self, email, phone=None, code='123456'):
        data = {
            'csrf_token': self._csrf('/web/signup'), 'login': email, 'name': 'Sita Sharma',
            'password': PASSWORD, 'confirm_password': PASSWORD,
        }
        if phone is not None:
            data['phone'] = phone
        with patch(f'{MODULE}._new_code', return_value=code):
            return self.url_open('/web/signup', data=data)

    def _verify(self, **data):
        return self.url_open('/web/signup/verify', data={'csrf_token': self._csrf(), **data})

    def _user(self, email):
        self.env.invalidate_all()
        return self.env['res.users'].search([('login', '=', email)])

    def _logged_in(self):
        return self.url_open('/web/login_successful').url.endswith('/web/login_successful')

    def test_code_comes_by_sms(self):
        self.assertIn('name="phone"', self.url_open('/web/signup').text)
        response = self._signup('sita@example.com', phone='984-1234567')
        self.assertIn('/web/signup/verify', response.url)
        self.assertIn('We texted a 6-digit code to <strong>984*****67</strong>', response.text)
        self.assertIn('Text me a new code', response.text)

        [call] = self.nestsms.calls
        self.assertEqual(call['payload'], {
            'to': '9841234567', 'template_id': TEMPLATE_ID, 'message_type': 'otp', 'variables': {'otp': '123456'},
        })
        user = self._user('sita@example.com')
        self.assertEqual(user._signup_channel(), 'sms')
        self.assertEqual(user._signup_validity(), 10, "The approved template says 10 minutes.")

        self.assertIn('4 tries left', self._verify(code='000000').text)
        self._verify(code='123456')
        user = self._user('sita@example.com')
        self.assertTrue(user.signup_email_verified)
        self.assertEqual(user.partner_id.sms_verified_phone, '9841234567')
        self.assertTrue(self._logged_in())

    def test_phone_required(self):
        response = self._signup('hari@example.com', phone='')
        self.assertIn('Enter your mobile number', response.text)
        self.assertFalse(self._user('hari@example.com'))

    def test_foreign_number_gets_email(self):
        response = self._signup('john@example.com', phone='+1 555 123 4567')
        self.assertIn('We emailed a 6-digit code', response.text)
        self.assertFalse(self.nestsms.calls)
        self._verify(code='123456')
        user = self._user('john@example.com')
        self.assertTrue(user.signup_email_verified)
        self.assertFalse(user.partner_id.sms_verified_phone, "Activated by email: the phone isn't proven.")

    def test_sms_refused_falls_back_to_email(self):
        self.nestsms.replies = [fake_response(400, {
            'success': False, 'error': "Template ID not found", 'code': 'TEMPLATE_NOT_FOUND',
        })]
        response = self._signup('gita@example.com', phone='9801234567')
        self.assertIn('We emailed a 6-digit code', response.text)
        self.assertEqual(self._user('gita@example.com')._signup_channel(), 'email')
        self.assertFalse(self.env.company._sms_otp_enabled('signup'), "A rejected template switches SMS codes off.")

    def test_switched_off(self):
        self.env.company.sms_otp_signup = False
        self.assertNotIn('name="phone"', self.url_open('/web/signup').text)
        response = self._signup('ram@example.com')
        self.assertIn('We emailed a 6-digit code', response.text)
        self.assertFalse(self.nestsms.calls)
