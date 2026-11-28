# Part of Odoo. See LICENSE file for full copyright and licensing details.

import itertools
import re
from unittest.mock import patch

from odoo.exceptions import AccessDenied
from odoo.tests import HttpCase, tagged
from odoo.tests.common import new_test_user

from odoo.addons.sms_nestsms.tests.common import TEMPLATE_ID, approve_otp, patch_nestsms

CODE = '123456'      # emailed
SMS_CODE = '654321'  # texted
MOBILE = '9841234567'
NEW_PASSWORD = 'N3w-Reset-Passw0rd'


@tagged('post_install', '-at_install')
class TestResetSms(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env['ir.config_parameter'].sudo().set_param('auth_signup.reset_password', 'True')
        cls.env.company.write({'sms_nestsms_api_key': 'nsms_live_test', 'sms_brand_name': 'Flagship-Store'})
        approve_otp(cls.env.company, 'reset')
        cls.user = new_test_user(cls.env, login='sita@example.com', password='Old-Passw0rd-123',
                                 groups='base.group_portal', email='sita@example.com', name='Sita Gurung')
        cls.user.partner_id.write({'phone': MOBILE, 'sms_verified_phone': MOBILE})

    def setUp(self):
        super().setUp()
        self.nestsms = patch_nestsms(self)
        codes = itertools.cycle([CODE, SMS_CODE])  # each request draws the email's code, then the SMS's
        self.startPatcher(patch('odoo.addons.auth_otp.models.auth_otp._new_code', side_effect=lambda: next(codes)))

    def _csrf(self, url='/web/reset_password'):
        return re.search(r'name="csrf_token" value="([^"]+)"', self.url_open(url).text).group(1)

    def _ask(self, login, method='sms'):
        return self.url_open('/web/reset_password', data={'csrf_token': self._csrf(), 'login': login, 'method': method})

    def _code(self, code):
        return self.url_open('/web/reset_password/code', data={
            'csrf_token': self._csrf('/web/reset_password/code'), 'code': code,
        })

    def _new(self, password):
        return self.url_open('/web/reset_password/new', data={
            'csrf_token': self._csrf('/web/reset_password/new'), 'password': password, 'confirm_password': password,
        })

    def _otp(self, user=None):
        return self.env['auth.otp'].sudo().search([('purpose', '=', 'reset'), ('user_id', '=', (user or self.user).id)])

    def _password_works(self, user, password):
        try:
            self.env['res.users'].authenticate(
                {'login': user.login, 'password': password, 'type': 'password'}, {'interactive': False})
        except AccessDenied:
            return False
        return True

    def test_sms_code_resets_the_password(self):
        page = self.url_open('/web/reset_password').text
        self.assertIn('reset_method_sms', page)
        self.assertIn('Email or verified mobile number', page)

        response = self._ask('sita@example.com')
        self.assertIn('texted a different one', response.text)
        [call] = self.nestsms.calls
        self.assertEqual(call['payload']['to'], MOBILE)
        self.assertEqual(call['payload']['template_id'], TEMPLATE_ID)
        self.assertEqual(call['payload']['variables']['otp'], SMS_CODE)
        otp = self._otp()
        self.assertEqual(otp.channels, 'email,sms', "SMS chosen: the email gets its own code too.")

        self.assertTrue(self._code(SMS_CODE).url.endswith('/web/reset_password/new'))
        self.assertEqual(otp.verified_by, 'sms', "The log says the SMS code was used.")
        self.assertIn('/web/login', self._new(NEW_PASSWORD).url)
        self.assertTrue(self._password_works(self.user, NEW_PASSWORD))

    def test_the_emailed_code_works_too_and_closes_both(self):
        self._ask('sita@example.com')
        self.assertTrue(self._code(CODE).url.endswith('/web/reset_password/new'))
        otp = self._otp()
        self.assertEqual(otp.verified_by, 'email')
        self.assertEqual(otp.state, 'verified')

    def test_the_verified_mobile_number_finds_the_account(self):
        response = self._ask('984-123-4567')
        self.assertEqual(len(self.nestsms.calls), 1)
        self.assertTrue(self._code(SMS_CODE).url.endswith('/web/reset_password/new'))
        self.assertIn(self.user.login, self.url_open('/web/reset_password/new').text)
        self.assertTrue(response.url.endswith('/web/reset_password/code'))

    def test_email_method_sends_no_sms(self):
        self._ask('sita@example.com', method='email')
        self.assertFalse(self.nestsms.calls)
        self.assertEqual(self._otp().channels, 'email')

    def test_unproven_number_gets_no_code(self):
        self.user.partner_id.sms_verified_phone = False
        self._ask('sita@example.com')
        self.assertFalse(self.nestsms.calls, "Never text a reset code to a number nobody proved.")
        self.assertEqual(self._otp().channels, 'email')
        # The number alone finds nothing: same answer as for an unknown account.
        self.url_open('/web/session/logout')
        response = self._ask(MOBILE)
        self.assertTrue(response.url.endswith('/web/reset_password/code'))
        self.assertEqual(len(self._otp()), 1)

    def test_staff_reset_by_email_only(self):
        staff = new_test_user(self.env, login='staff@example.com', password='Old-Passw0rd-123',
                              groups='base.group_user', email='staff@example.com')
        staff.partner_id.sms_verified_phone = '9801112222'
        self._ask('staff@example.com')
        self.assertFalse(self.nestsms.calls)
        self.assertEqual(self._otp(staff).channels, 'email')
        self.url_open('/web/session/logout')
        self._ask('9801112222')
        self.assertEqual(len(self._otp(staff)), 1, "A staff account isn't found by its number.")

    def test_a_number_two_accounts_proved_finds_none(self):
        other = new_test_user(self.env, login='hari@example.com', groups='base.group_portal', email='hari@example.com')
        other.partner_id.sms_verified_phone = MOBILE
        self._ask(MOBILE)
        self.assertFalse(self.nestsms.calls)
        self.assertFalse(self._otp() | self._otp(other))

    def test_switched_off(self):
        self.env.company._sms_otp_set_approved('reset', False)
        self.assertNotIn('reset_method_sms', self.url_open('/web/reset_password').text)
        self._ask('sita@example.com', method='sms')
        self.assertFalse(self.nestsms.calls)
        self.assertEqual(self._otp().channels, 'email')
