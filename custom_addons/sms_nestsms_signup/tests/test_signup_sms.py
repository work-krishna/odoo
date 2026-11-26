# Part of Odoo. See LICENSE file for full copyright and licensing details.

import re
from unittest.mock import patch

from odoo.tests import HttpCase, tagged

from odoo.addons.auth_signup_email_otp.models.res_users import ResUsers
from odoo.addons.sms_nestsms.tests.common import TEMPLATE_ID, approve_otp, fake_response, patch_nestsms

CODE = '123456'
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
        self.startPatcher(patch('odoo.addons.auth_otp.models.auth_otp._new_code', return_value=CODE))
        # Capture the activation email instead of rendering and sending it.
        self.emailed = self.startPatcher(patch.object(ResUsers, '_signup_email_sender'))

    def _csrf(self, url='/web/login'):
        return re.search(r'name="csrf_token" value="([^"]+)"', self.url_open(url).text).group(1)

    def _signup(self, email, phone=None):
        data = {
            'csrf_token': self._csrf('/web/signup'), 'login': email, 'name': 'Sita Sharma',
            'password': PASSWORD, 'confirm_password': PASSWORD,
        }
        if phone is not None:
            data['phone'] = phone
        return self.url_open('/web/signup', data=data)

    def _verify(self, **data):
        return self.url_open('/web/signup/verify', data={'csrf_token': self._csrf(), **data})

    def _user(self, email):
        self.env.invalidate_all()
        return self.env['res.users'].search([('login', '=', email)])

    def _logged_in(self):
        return self.url_open('/web/login_successful').url.endswith('/web/login_successful')

    def _emailed_codes(self):
        return [call.args[1] for call in self.emailed.call_args_list]

    def test_same_code_by_email_and_sms(self):
        self.assertIn('name="phone"', self.url_open('/web/signup').text)
        response = self._signup('sita@example.com', phone='984-1234567')
        self.assertIn('/web/signup/verify', response.url)
        # The activation page names both places the code went.
        self.assertIn('<strong>s**a@example.com</strong>', response.text)
        self.assertIn('<strong>984*****67</strong> by SMS', response.text)

        self.assertEqual(self._emailed_codes(), [CODE])
        [call] = self.nestsms.calls
        self.assertEqual(call['payload'], {
            'to': '9841234567', 'template_id': TEMPLATE_ID, 'message_type': 'otp', 'variables': {'otp': CODE},
        })
        user = self._user('sita@example.com')
        self.assertEqual(user._signup_pending().channels, 'email,sms')
        self.assertEqual(user._signup_pending()._otp_minutes(), 10, "The approved text says 10 minutes.")

        self.assertIn('4 tries left', self._verify(code='000000').text)
        self._verify(code=CODE)
        user = self._user('sita@example.com')
        self.assertTrue(user.signup_email_verified)
        self.assertTrue(self._logged_in())
        # The code went to both: entering it proves the email or the phone, not the phone.
        self.assertFalse(user.partner_id.sms_verified_phone)

    def test_resend_goes_to_both(self):
        self._signup('hari@example.com', phone='9801234567')
        user = self._user('hari@example.com')
        user._signup_pending().write({'sent_at': user._signup_pending().sent_at.replace(year=2020)})
        self.assertIn('We sent you a new code by email and SMS.', self._verify(resend='1').text)
        self.assertEqual(len(self._emailed_codes()), 2)
        self.assertEqual(len(self.nestsms.calls), 2)

    def test_phone_required(self):
        response = self._signup('ram@example.com', phone='')
        self.assertIn('Enter your mobile number', response.text)
        self.assertFalse(self._user('ram@example.com'))

    def test_foreign_number_gets_email_only(self):
        response = self._signup('john@example.com', phone='+1 555 123 4567')
        self.assertIn('<strong>j**n@example.com</strong>', response.text)
        self.assertNotIn('by SMS', response.text)
        self.assertFalse(self.nestsms.calls)
        self._verify(code=CODE)
        self.assertTrue(self._user('john@example.com').signup_email_verified)

    def test_sms_refused_still_emailed(self):
        self.nestsms.replies = [fake_response(400, {
            'success': False, 'error': "Template ID not found", 'code': 'TEMPLATE_NOT_FOUND',
        })]
        response = self._signup('gita@example.com', phone='9801234567')
        self.assertNotIn('by SMS', response.text)
        self.assertEqual(self._user('gita@example.com')._signup_pending().channels, 'email')
        self.assertFalse(self.env.company._sms_otp_enabled('signup'), "A rejected template switches SMS codes off.")

    def test_switched_off(self):
        self.env.company.sms_otp_signup = False
        self.assertNotIn('name="phone"', self.url_open('/web/signup').text)
        self._signup('mina@example.com')
        self.assertEqual(self._emailed_codes(), [CODE])
        self.assertFalse(self.nestsms.calls)
