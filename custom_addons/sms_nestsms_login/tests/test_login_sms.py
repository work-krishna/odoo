# Part of Odoo. See LICENSE file for full copyright and licensing details.

import re

from odoo.tests import HttpCase, tagged
from odoo.tests.common import new_test_user

from odoo.addons.sms_nestsms.tests.common import TEMPLATE_ID, approve_otp, patch_nestsms


@tagged('post_install', '-at_install')
class TestLoginSms(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.company.write({
            'sms_nestsms_api_key': 'nsms_live_test',
            'sms_brand_name': 'Flagship-Store',
        })
        approve_otp(cls.env.company, 'login')
        cls.customer = new_test_user(cls.env, login='sita@example.com', groups='base.group_portal', name='Sita Gurung')
        cls.customer.partner_id.write({'phone': '9841234567', 'sms_verified_phone': '9841234567'})

    def setUp(self):
        super().setUp()
        self.nestsms = patch_nestsms(self)

    def _csrf(self, url='/web/login/sms'):
        return re.search(r'name="csrf_token" value="([^"]+)"', self.url_open(url).text).group(1)

    def _post(self, **data):
        return self.url_open('/web/login/sms', data={'csrf_token': self._csrf(), **data})

    def _sent_code(self):
        return self.nestsms.calls[-1]['payload']['variables']['otp']

    def _session_uid(self):
        return self.make_jsonrpc_request('/web/session/get_session_info', {}).get('uid')

    def test_login_with_code(self):
        self.assertIn('Log in with an SMS code', self.url_open('/web/login').text)

        response = self._post(phone='+977 984-1234567')
        self.assertIn('984*****67', response.text)
        [call] = self.nestsms.calls
        self.assertEqual(call['payload']['template_id'], TEMPLATE_ID)
        self.assertEqual(call['payload']['to'], '9841234567')

        self.assertIn('4 tries left', self._post(code='000000' if self._sent_code() != '000000' else '111111').text)
        response = self._post(code=self._sent_code())
        self.assertEqual(self._session_uid(), self.customer.id)
        self.assertNotIn('/web/login', response.url)

    def test_unproven_number_cannot_log_in(self):
        self.customer.partner_id.sms_verified_phone = False
        response = self._post(phone='9841234567')
        self.assertIn('If this number belongs to an account', response.text, "Same answer as for a real account.")
        self.assertFalse(self.nestsms.calls)
        self.assertIn("That code is not right", self._post(code='123456').text)
        self.assertIn('/web/login', self.url_open('/my').url, "Still logged out.")

    def test_staff_cannot_log_in_by_sms(self):
        staff = new_test_user(self.env, login='staff@example.com', groups='base.group_user')
        staff.partner_id.sms_verified_phone = '9801234567'
        self._post(phone='9801234567')
        self.assertFalse(self.nestsms.calls)

    def test_shared_number_is_ambiguous(self):
        other = new_test_user(self.env, login='gita@example.com', groups='base.group_portal')
        other.partner_id.sms_verified_phone = '9841234567'
        self._post(phone='9841234567')
        self.assertFalse(self.nestsms.calls)

    def test_switched_off(self):
        self.env.company.sms_otp_login = False
        self.assertNotIn('Log in with an SMS code', self.url_open('/web/login').text)
        self.assertEqual(self.url_open('/web/login/sms').status_code, 404)

    def test_restart(self):
        self._post(phone='9841234567')
        response = self._post(restart='1')
        self.assertIn('name="phone"', response.text)
