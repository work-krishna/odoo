import re
from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.exceptions import AccessDenied
from odoo.tests import HttpCase, tagged
from odoo.tests.common import new_test_user

from odoo.addons.auth_signup_email_otp.models.res_users import VALIDITY_PARAM

# Codes and link tokens come from the one-time-code engine.
MODULE = 'odoo.addons.auth_otp.models.auth_otp'
PASSWORD = 'Str0ng-Signup-Pass'


@tagged('post_install', '-at_install')
class TestSignupEmailOtp(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env['ir.config_parameter'].sudo().set_param('auth_signup.invitation_scope', 'b2c')
        if 'website' in cls.env:  # there, each website decides whether anyone may sign up
            cls.env['website'].search([]).auth_signup_uninvited = 'b2c'

    def _csrf(self, url='/web/login'):
        return re.search(r'name="csrf_token" value="([^"]+)"', self.url_open(url).text).group(1)

    def _codes(self, code, token='link-token'):
        return patch(f'{MODULE}._new_code', return_value=code), patch(f'{MODULE}._new_token', return_value=token)

    def _signup(self, email, code='123456', token='link-token'):
        patch_code, patch_token = self._codes(code, token)
        with patch_code, patch_token:
            return self.url_open('/web/signup', data={
                'csrf_token': self._csrf('/web/signup'), 'login': email, 'name': 'Sita Sharma',
                'password': PASSWORD, 'confirm_password': PASSWORD,
            })

    def _verify(self, **data):
        return self.url_open('/web/signup/verify', data={'csrf_token': self._csrf(), **data})

    def _user(self, email):
        self.env.invalidate_all()
        return self.env['res.users'].search([('login', '=', email)])

    def _logged_in(self):
        return self.url_open('/web/login_successful').url.endswith('/web/login_successful')

    def _age(self, user, **delta):
        """Move the latest code's clock back (even a used-up one: it sets the resend cooldown)."""
        pending = self.env['auth.otp'].sudo().search([('purpose', '=', 'signup'), ('user_id', '=', user.id)], limit=1)
        pending.write({'sent_at': pending.sent_at - timedelta(**delta),
                       'expires_at': pending.expires_at - timedelta(**delta)})

    def test_signup_needs_the_emailed_code(self):
        response = self._signup('sita@example.com')
        self.assertIn('/web/signup/verify', response.url)
        self.assertIn('s**a@example.com', response.text)
        user = self._user('sita@example.com')
        self.assertFalse(user.signup_activated)
        self.assertFalse(user.signup_email_verified)
        self.assertFalse(self._logged_in())

        self.assertIn('4 tries left', self._verify(code='000000').text)
        self._verify(code='123 456')
        user = self._user('sita@example.com')
        self.assertTrue(user.signup_activated)
        self.assertTrue(user.signup_email_verified, "The emailed code proves the address.")
        self.assertTrue(self._logged_in())
        self.assertNotIn('o_verify_email_bar', self.url_open('/').text)

    def test_activation_link_works_on_another_device(self):
        self._signup('hari@example.com', token='hari-link')
        self.url_open('/web/session/logout')
        response = self.url_open('/web/signup/activate?token=hari-link')
        self.assertIn('/web/login', response.url)
        self.assertIn('Your account is activated', response.text)
        self.assertTrue(self._user('hari@example.com').signup_email_verified)

        login = self.url_open('/web/login', data={
            'csrf_token': self._csrf(), 'login': 'hari@example.com', 'password': PASSWORD,
        })
        self.assertNotIn('/web/signup/verify', login.url)
        self.assertTrue(self._logged_in())
        self.assertIn('not valid', self.url_open('/web/signup/activate?token=hari-link').text)

    def test_login_before_activation_lands_on_the_activation_page(self):
        self._signup('mina@example.com', code='987654')
        self.url_open('/web/session/logout')
        login = self.url_open('/web/login', data={
            'csrf_token': self._csrf(), 'login': 'mina@example.com', 'password': PASSWORD,
            'redirect': '/web/login_successful?from=shop',
        })
        self.assertIn('/web/signup/verify', login.url)
        self.assertFalse(self._logged_in())
        done = self._verify(code='987654', redirect='/web/login_successful?from=shop')
        self.assertIn('from=shop', done.url)
        self.assertTrue(self._logged_in())

    def test_expired_code_and_link_then_a_fresh_code(self):
        self._signup('gita@example.com', code='111111', token='old-link')
        user = self._user('gita@example.com')
        self._age(user, minutes=20)
        self.assertIn('has expired', self._verify(code='111111').text)
        self.assertIn('has expired', self.url_open('/web/signup/activate?token=old-link').text)

        patch_code, patch_token = self._codes('222222', 'new-link')
        with patch_code, patch_token:  # coming back to the page emails new ones
            self.assertIn('emailed you a new one', self.url_open('/web/signup/verify').text)
        self.assertIn('not valid', self.url_open('/web/signup/activate?token=old-link').text)
        self._verify(code='222222')
        self.assertTrue(self._logged_in())

    def test_wrong_codes_use_it_up_and_resending_waits_a_minute(self):
        self._signup('ram@example.com', code='333333')
        for _attempt in range(4):
            self._verify(code='000000')
        self.assertIn('cannot be used any more', self._verify(code='000000').text)
        self.assertIn('can no longer be used', self._verify(code='333333').text)

        self.assertIn('less than a minute ago', self._verify(resend='1').text)
        self._age(self._user('ram@example.com'), minutes=2)
        patch_code, patch_token = self._codes('444444')
        with patch_code, patch_token:
            self.assertIn('new code and link', self._verify(resend='1').text)
        self._verify(code='444444')
        self.assertTrue(self._logged_in())

    def test_other_accounts_are_not_affected(self):
        new_test_user(self.env, 'portal_otp_user', groups='base.group_portal', email='portal@example.com')
        self.authenticate('portal_otp_user', 'portal_otp_user')
        self.assertTrue(self._logged_in())

        # A password reset link proves the address as well.
        patch_code, patch_token = self._codes('555555')
        with patch_code, patch_token:
            self.env['res.users'].sudo().signup({'login': 'reset@example.com', 'name': 'Reset', 'password': PASSWORD})
        user = self._user('reset@example.com')
        self.assertFalse(user.signup_email_verified)
        user.partner_id.signup_prepare(signup_type='reset')
        self.env['res.users'].sudo().signup({'password': 'An0ther-Signup-Pass'}, user.partner_id._generate_signup_token())
        self.assertTrue(user.signup_email_verified)
        self.assertFalse(user._signup_pending())

    def test_password_api_login_refused_until_activated(self):
        patch_code, patch_token = self._codes('666666')
        with patch_code, patch_token:
            self.env['res.users'].sudo().signup({'login': 'api@example.com', 'name': 'Api', 'password': PASSWORD})
        credential = {'login': 'api@example.com', 'password': PASSWORD, 'type': 'password'}
        with self.assertRaises(AccessDenied):
            self.env['res.users'].authenticate(credential, {'interactive': False})
        self._user('api@example.com')._signup_mark_verified()
        self.assertEqual(self.env['res.users'].authenticate(credential, {'interactive': False})['uid'],
                         self._user('api@example.com').id)

    def test_validity_setting_and_welcome_email(self):
        self.env['ir.config_parameter'].sudo().set_param(VALIDITY_PARAM, '5')
        patch_code, patch_token = self._codes('777777')
        with patch_code, patch_token:
            self.env['res.users'].sudo().signup({'login': 'late@example.com', 'name': 'Late', 'password': PASSWORD})
        user = self._user('late@example.com')
        pending = user._signup_pending()
        self.assertEqual(pending.expires_at - pending.sent_at, timedelta(minutes=5))
        self.assertLess(pending.sent_at, fields.Datetime.now() + timedelta(seconds=1))
        self.assertNotIn('777777', pending.email_code_hash)

        welcome = self.env.ref('auth_signup.mail_template_user_signup_account_created')
        self.assertFalse(welcome.send_mail(user.id), "held back until the account is activated")
        user._signup_mark_verified()
        self.assertTrue(welcome.send_mail(user.id))

    # Confirming the email address later (an account activated with the SMS code)
    # ------------------------------------------------------------------

    def _activated_by_sms(self, email):
        patch_code, patch_token = self._codes('121212')
        with patch_code, patch_token:
            self.env['res.users'].sudo().signup({'login': email, 'name': 'Sita', 'password': PASSWORD, 'email': email})
        user = self._user(email)
        user._signup_pending().verified_by = 'sms'
        user._signup_mark_verified(user._signup_pending())
        self.assertTrue(user.signup_activated)
        self.assertFalse(user.signup_email_verified)
        return user

    def _post_verify_email(self, **data):
        return self.url_open('/my/verify-email', data={'csrf_token': self._csrf('/my/verify-email'), **data})

    def test_confirm_email_later_with_the_code(self):
        self._activated_by_sms('sms@example.com')
        welcome = self.env.ref('auth_signup.mail_template_user_signup_account_created')
        self.assertFalse(welcome.send_mail(self._user('sms@example.com').id), "No mail to an unproven address yet.")
        self.authenticate('sms@example.com', PASSWORD)
        self.assertNotIn('/web/signup/verify', self.url_open('/my').url, "Nothing is blocked.")
        home = self.url_open('/').text
        self.assertIn('o_verify_email_bar', home)
        self.assertIn('href="/my/verify-email"', home)

        page = self.url_open('/my/verify-email').text
        self.assertIn('Email me a code', page)
        self.assertNotIn('o_verify_email_bar', page)
        patch_code, patch_token = self._codes('343434')
        with patch_code, patch_token:
            sent = self._post_verify_email(send='1').text
        self.assertIn('We emailed you a code and a link.', sent)
        self.assertIn('<strong>sms@example.com</strong>', sent)

        self.assertIn('4 tries left', self._post_verify_email(code='000000').text)
        self.assertIn('Email address confirmed', self._post_verify_email(code='343434').text)
        self.assertTrue(self._user('sms@example.com').signup_email_verified)
        self.assertNotIn('o_verify_email_bar', self.url_open('/').text)
        self.assertEqual(self.url_open('/my/verify-email').url.removeprefix(self.base_url()), '/')

    def test_confirm_email_later_with_the_link(self):
        user = self._activated_by_sms('link@example.com')
        patch_code, patch_token = self._codes('565656', 'confirm-link')
        with patch_code, patch_token:
            self.assertTrue(user._verify_email_send()[0])
        self.assertIn('Email address confirmed', self.url_open('/web/verify-email?token=confirm-link').text)
        self.assertTrue(self._user('link@example.com').signup_email_verified)
        self.assertIn('not valid', self.url_open('/web/verify-email?token=confirm-link').text)

    def test_confirm_email_refused_after_the_address_changed(self):
        user = self._activated_by_sms('moved@example.com')
        patch_code, patch_token = self._codes('787878', 'moved-link')
        with patch_code, patch_token:
            user._verify_email_send()
        user.email = 'other@example.com'
        self.assertIn('changed since', self.url_open('/web/verify-email?token=moved-link').text)
        self.assertFalse(self._user('moved@example.com').signup_email_verified)
