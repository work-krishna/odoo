from unittest.mock import patch

from odoo.tests import TransactionCase, tagged
from odoo.addons.auth_totp.models.totp import TOTP


@tagged('post_install', '-at_install')
class TestKw2faResUsers(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._has_calendar_field = (
            'calendar_default_privacy' in
            cls.env['res.users.settings']._fields
        )
        cls.user = cls._create_test_user(
            'Test User', 'test_2fa_user', 'test_2fa@example.com')
        cls.admin = cls.env.ref('base.user_root')
        cls.test_secret = 'GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ'  # nosec

    @classmethod
    def _create_test_user(cls, name, login, email):
        user = cls.env['res.users'].create({
            'name': name,
            'login': login,
            'email': email,
        })
        if cls._has_calendar_field and user.res_users_settings_ids:
            user.res_users_settings_ids.sudo().write({
                'calendar_default_privacy': 'public',
            })
        return user

    def test_mfa_type_regular_user_returns_totp(self):
        self.assertEqual(
            self.user._mfa_type(),
            'totp',
            'Regular user should always return totp')

    def test_mfa_type_admin_returns_parent(self):
        result = self.admin._mfa_type()
        self.assertIn(
            result,
            [None, 'totp'],
            'Admin should use parent implementation')

    def test_mfa_url_without_totp_returns_setup(self):
        self.assertFalse(self.user.totp_enabled)
        self.assertEqual(
            self.user._mfa_url(),
            '/kw_2fa/setup_totp',
            'User without TOTP should be redirected to setup page')

    def test_mfa_url_with_totp_returns_login(self):
        self.user.sudo().totp_secret = self.test_secret
        self.assertTrue(self.user.totp_enabled)
        self.assertEqual(
            self.user._mfa_url(),
            '/web/login/totp',
            'User with TOTP should be redirected to login/totp')

    def test_generate_totp_qr_data_returns_dict(self):
        result = self.user._kw_generate_totp_qr_data('test.issuer.com')
        self.assertIn('totp_secret', result)
        self.assertIn('totp_qr', result)
        self.assertIn('formatted_totp_secret', result)

    def test_generate_totp_qr_data_secret_length(self):
        result = self.user._kw_generate_totp_qr_data()
        self.assertEqual(
            len(result['totp_secret']),
            32,
            'Secret should be 32 chars (160 bits in base32)')

    def test_generate_totp_qr_data_formatted_secret(self):
        result = self.user._kw_generate_totp_qr_data()
        parts = result['formatted_totp_secret'].split(' ')
        for part in parts:
            self.assertEqual(
                len(part),
                4,
                'Formatted secret should have 4-char groups')

    def test_totp_try_setting_valid_code(self):
        with patch.object(TOTP, 'match', return_value=123456):
            result = self.user._kw_totp_try_setting(self.test_secret, 123456)
        self.assertTrue(result, 'Valid code should return True')
        self.assertEqual(
            self.user.sudo().totp_secret,
            self.test_secret.upper(),
            'Secret should be saved')

    def test_totp_try_setting_invalid_code(self):
        user2 = self._create_test_user(
            'Test User 2', 'test_2fa_user2', 'test_2fa2@example.com')
        with patch.object(TOTP, 'match', return_value=None):
            result = user2._kw_totp_try_setting(self.test_secret, 999999)
        self.assertFalse(result, 'Invalid code should return False')
        self.assertFalse(
            user2.sudo().totp_secret,
            'Secret should not be saved')

    def test_totp_try_setting_already_enabled(self):
        user3 = self._create_test_user(
            'Test User 3', 'test_2fa_user3', 'test_2fa3@example.com')
        user3.sudo().totp_secret = self.test_secret
        self.assertTrue(user3.totp_enabled)
        result = user3._kw_totp_try_setting('NEWSECRETNEWSECRET', 123456)
        self.assertFalse(
            result,
            'Should return False if TOTP already enabled')
        self.assertEqual(
            user3.sudo().totp_secret,
            self.test_secret,
            'Original secret should remain unchanged')
