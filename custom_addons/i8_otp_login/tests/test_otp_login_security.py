# -*- coding: utf-8 -*-
import re
from unittest.mock import patch

from odoo.tests import HttpCase, tagged
from odoo.tests.common import new_test_user

from odoo.addons.i8_otp_login.controllers import main as otp_main

CODE = '482913'


@tagged('post_install', '-at_install')
class TestOtpLoginSecurity(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.customer = new_test_user(cls.env, login='sita@example.com', email='sita@example.com',
                                     groups='base.group_portal', name='Sita Gurung')
        cls.staff = new_test_user(cls.env, login='boss@example.com', email='boss@example.com',
                                  groups='base.group_user,base.group_system', name='Boss')
        cls.env['ir.config_parameter'].sudo().set_param('auth_signup.invitation_scope', 'b2b')
        cls.env['website'].search([]).auth_signup_uninvited = 'b2b'

    def setUp(self):
        super().setUp()
        otp_main._sends.clear()
        self.new_code = self.startPatcher(patch.object(otp_main, '_new_code', return_value=CODE))
        self.url_open('/web/login')  # a session

    def _send(self, email):
        return self.make_jsonrpc_request('/otp-login/send', {'email': email})

    def _verify(self, code, redirect='/my'):
        return self.make_jsonrpc_request('/otp-login/verify', {'code': code, 'redirect': redirect})

    def _uid(self):
        try:
            return self.make_jsonrpc_request('/web/session/get_session_info', {}).get('uid')
        except Exception:  # noqa: BLE001  logged out: session expired
            return None

    def _new_visitor(self):
        self.opener.cookies.clear()
        self.url_open('/web/login')

    def test_customer_logs_in(self):
        self.assertEqual(self._send('sita@example.com'), {'status': 'success'})
        result = self._verify(CODE)
        self.assertEqual(result['status'], 'success')
        self.assertEqual(self._uid(), self.customer.id)
        self.assertEqual(result['redirect'], '/my')

    def test_staff_get_no_code(self):
        self.assertEqual(self._send('boss@example.com'), {'status': 'success'}, "Same answer as for a customer.")
        self.new_code.assert_not_called()
        self.assertEqual(self._verify(CODE)['status'], 'error')
        self.assertFalse(self._uid())

    def test_guessing_is_capped(self):
        self._send('sita@example.com')
        for left in (4, 3, 2, 1):
            self.assertIn(f'{left} tries left', self._verify('000000')['message'])
        self.assertIn('Too many wrong codes', self._verify('000000')['message'])
        self.assertEqual(self._verify(CODE)['status'], 'error', "The code is dead after 5 wrong tries.")
        self.assertFalse(self._uid())

    def test_code_expires(self):
        self._send('sita@example.com')
        with patch.object(otp_main.time, 'time', return_value=otp_main.time.time() + 11 * 60):
            self.assertIn('expired', self._verify(CODE)['message'])
        self.assertFalse(self._uid())

    def test_resend_cooldown_and_hourly_cap(self):
        self._send('sita@example.com')
        self.assertIn('wait a minute', self._send('sita@example.com')['message'])
        for _i in range(4):
            self._new_visitor()
            self.assertEqual(self._send('sita@example.com')['status'], 'success')
        self._new_visitor()
        self.assertIn('Too many codes', self._send('sita@example.com')['message'])
        self.assertEqual(self.new_code.call_count, 5)

    def test_no_account_creation_when_signup_closed(self):
        self.assertEqual(self._send('stranger@example.com'), {'status': 'success'})
        self.new_code.assert_not_called()
        self.assertEqual(self._verify(CODE)['status'], 'error')
        self.assertFalse(self.env['res.users'].search([('login', '=', 'stranger@example.com')]))

    def test_account_creation_when_signup_open(self):
        self.env['website'].search([]).auth_signup_uninvited = 'b2c'
        self.env['ir.config_parameter'].sudo().set_param('auth_signup.invitation_scope', 'b2c')
        self._send('newbie@example.com')
        self.assertEqual(self._verify(CODE)['status'], 'success')
        user = self.env['res.users'].search([('login', '=', 'newbie@example.com')])
        self.assertTrue(user.share)
        self.assertEqual(self._uid(), user.id)

    def test_redirect_stays_on_site(self):
        self._send('sita@example.com')
        result = self._verify(CODE, redirect='//evil.example.com/steal')
        self.assertFalse(result['redirect'].startswith('//'))
        self.assertNotIn('evil.example.com', result['redirect'])

    def test_credential_cannot_be_forged(self):
        page = self.url_open('/web/login')
        csrf = re.search(r'name="csrf_token" value="([^"]+)"', page.text).group(1)
        self.url_open('/web/login', data={
            'csrf_token': csrf, 'login': 'sita@example.com', 'type': 'i8_email_otp', 'proof': 'x',
        })
        self.assertFalse(self._uid())

    def test_code_not_logged(self):
        with self.assertLogs('odoo.addons.i8_otp_login', level='DEBUG') as logs:
            otp_main._logger.debug("start")
            self._send('sita@example.com')
        self.assertFalse([line for line in logs.output if CODE in line])
