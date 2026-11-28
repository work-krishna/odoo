import re
from unittest.mock import patch

from odoo.exceptions import AccessDenied
from odoo.tests import HttpCase, tagged
from odoo.tests.common import new_test_user

MODULE = 'odoo.addons.auth_otp.models.auth_otp'
CODE = '246813'
NEW_PASSWORD = 'N3w-Reset-Passw0rd'


@tagged('post_install', '-at_install')
class TestPasswordResetByCode(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env['ir.config_parameter'].sudo().set_param('auth_signup.reset_password', 'True')
        cls.user = new_test_user(cls.env, login='mina@example.com', password='Old-Passw0rd-123',
                                 groups='base.group_portal', email='mina@example.com', name='Mina Rai')

    def setUp(self):
        super().setUp()
        self.startPatcher(patch(f'{MODULE}._new_code', return_value=CODE))

    def _csrf(self, url='/web/reset_password'):
        return re.search(r'name="csrf_token" value="([^"]+)"', self.url_open(url).text).group(1)

    def _ask(self, login, method='email'):
        return self.url_open('/web/reset_password', data={'csrf_token': self._csrf(), 'login': login, 'method': method})

    def _code(self, code):
        return self.url_open('/web/reset_password/code', data={
            'csrf_token': self._csrf('/web/reset_password/code'), 'code': code,
        })

    def _new(self, password, confirm=None):
        return self.url_open('/web/reset_password/new', data={
            'csrf_token': self._csrf('/web/reset_password/new'), 'password': password,
            'confirm_password': password if confirm is None else confirm,
        })

    def _otps(self):
        return self.env['auth.otp'].sudo().search([('purpose', '=', 'reset'), ('user_id', '=', self.user.id)])

    def _password_works(self, password):
        try:
            self.env['res.users'].authenticate(
                {'login': self.user.login, 'password': password, 'type': 'password'}, {'interactive': False})
        except AccessDenied:
            return False
        return True

    def test_email_code_resets_the_password(self):
        page = self.url_open('/web/reset_password').text
        self.assertIn('Reset your password', page)
        self.assertNotIn('reset_method_sms', page, "No SMS option while SMS codes are off.")

        response = self._ask('Mina@Example.com')
        self.assertTrue(response.url.endswith('/web/reset_password/code'))
        self.assertIn('we emailed it a 6-digit code', response.text)
        [otp] = self._otps()
        self.assertEqual(otp.channels, 'email')
        self.assertEqual(otp.email, 'mina@example.com')

        self.assertIn('4 tries left', self._code('000000').text)
        self.assertTrue(self._code(CODE).url.endswith('/web/reset_password/new'))
        self.assertEqual(otp.verified_by, 'email')

        self.assertIn('Please type them again', self._new(NEW_PASSWORD, 'something-else').text)
        done = self._new(NEW_PASSWORD)
        self.assertIn('/web/login', done.url)
        self.assertIn('Your password is changed', done.text)
        self.assertTrue(self._password_works(NEW_PASSWORD))
        self.assertFalse(self._password_works('Old-Passw0rd-123'))
        # The proof is used up.
        self.assertTrue(self.url_open('/web/reset_password/new').url.endswith('/web/reset_password'))

    def test_unknown_account_gets_the_same_answers(self):
        response = self._ask('nobody@example.com')
        self.assertTrue(response.url.endswith('/web/reset_password/code'))
        self.assertIn('we emailed it a 6-digit code', response.text)
        self.assertFalse(self.env['auth.otp'].sudo().search([('purpose', '=', 'reset')]))
        for left in (4, 3, 2, 1):
            self.assertIn(f'{left} tries left', self._code(CODE).text)
        self.assertIn('cannot be used any more', self._code(CODE).text)
        self.assertIn('can no longer be used', self._code(CODE).text)

    def test_a_new_code_waits_a_minute(self):
        self._ask('mina@example.com')
        self.assertIn('less than a minute ago', self._ask('mina@example.com').text)
        self.assertEqual(len(self._otps()), 1)

    def test_new_password_needs_the_code(self):
        self.assertTrue(self.url_open('/web/reset_password/new').url.endswith('/web/reset_password'))
        self._ask('mina@example.com')
        self.assertTrue(self.url_open('/web/reset_password/new').url.endswith('/web/reset_password'))
        self.assertTrue(self.url_open('/web/reset_password/code').url.endswith('/web/reset_password/code'))

    def test_the_code_also_proves_the_email(self):
        self.user.signup_email_verified = False
        self._ask('mina@example.com')
        self._code(CODE)
        self.assertTrue(self.user.signup_email_verified)

    def test_emailed_links_still_work(self):
        self.user.partner_id.signup_prepare(signup_type='reset')
        token = self.user.partner_id._generate_signup_token()
        page = self.url_open(f'/web/reset_password?token={token}').text
        self.assertIn('name="confirm_password"', page)
        self.assertNotIn('Send code', page)

    def test_changed_email_must_be_confirmed_again(self):
        self.assertTrue(self.user.signup_email_verified)
        self.user.partner_id.email = 'MINA@example.com'  # same address
        self.assertTrue(self.user.signup_email_verified)
        self.user.partner_id.email = 'mina.rai@example.com'
        self.assertFalse(self.user.signup_email_verified)

        welcome = self.env.ref('auth_signup.mail_template_user_signup_account_created')
        with patch.object(type(welcome), 'send_mail') as send_mail:
            self.user._signup_mark_email_verified()
        self.assertTrue(self.user.signup_email_verified)
        send_mail.assert_not_called()  # no second welcome for a changed address

    def test_confirm_email_page_returns_where_asked(self):
        self.user.signup_email_verified = False
        self.authenticate('mina@example.com', 'Old-Passw0rd-123')
        page = self.url_open('/my/verify-email?redirect=/my/account').text
        self.assertIn('name="redirect" value="/my/account"', page)
        self.assertIn('href="/my/account">Not now', page)
        self.assertNotIn('evil.example', self.url_open('/my/verify-email?redirect=//evil.example').text)
