# Part of Odoo. See LICENSE file for full copyright and licensing details.

from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.tests import TransactionCase, tagged

from odoo.addons.auth_otp.models import auth_otp as otp_module
from odoo.addons.auth_otp.models.auth_otp import CHANNELS, DEFAULT_VALIDITY

CODE = '482913'


@tagged('post_install', '-at_install')
class TestAuthOtp(TransactionCase):

    def setUp(self):
        super().setUp()
        self.Otp = self.env['auth.otp']
        self.startPatcher(patch.object(otp_module, '_new_code', return_value=CODE))
        self.emails = []   # (otp, code, token) the email sender got
        self.texts = []    # (phone, code) the fake SMS channel got
        self.sms_on = True
        test = self

        def fake_send_sms(otp, code):
            test.texts.append((otp.phone, code))
            return True, False
        # Patch the registry's final class, so channel modules installed alongside (sms_nestsms)
        # don't change what is tested here: the engine alone, with a fake SMS channel.
        self.OtpClass = type(self.Otp)
        self.startPatcher(patch.object(self.OtpClass, '_otp_sms_available', lambda self, purpose, company: test.sms_on))
        self.startPatcher(patch.object(self.OtpClass, '_otp_send_sms', fake_send_sms))
        self.startPatcher(patch.object(self.OtpClass, '_otp_normalize_phone',
                                       lambda self, phone: ''.join(ch for ch in phone or '' if ch.isdigit()) or False))
        self.startPatcher(patch.object(self.OtpClass, '_otp_sms_max_validity', lambda self, purpose, company: None))
        self.startPatcher(patch.object(self.OtpClass, '_otp_policy', lambda self, purpose, company: {
            'channels': CHANNELS, 'validity': DEFAULT_VALIDITY}))

    def _email_sender(self, otp, code, token):
        self.emails.append((otp, code, token))

    def _issue(self, purpose='signup', **kwargs):
        kwargs.setdefault('email_sender', self._email_sender)
        return self.Otp._otp_issue(purpose, **kwargs)

    def test_one_code_on_every_channel(self):
        result = self._issue(email='Sita@Example.com', phone='+977 984-1234567')
        self.assertFalse(result['error'])
        self.assertEqual(result['channels'], ['email', 'sms'])
        self.assertEqual([code for _otp, code, _t in self.emails], [CODE])
        self.assertEqual(self.texts, [('9779841234567', CODE)], "The same code by SMS.")
        otp = result['otp']
        self.assertEqual(otp.email, 'sita@example.com')
        self.assertEqual(otp._otp_sent_to(), {'email': 's**a@example.com', 'sms': '977*****67'})
        self.assertNotIn(CODE, otp.sudo().code_hash)

        record, error = self.Otp._otp_verify('signup', f' {CODE[:3]} {CODE[3:]} ', email='sita@example.com')
        self.assertEqual(record, otp)
        self.assertEqual(otp.state, 'verified')
        self.assertFalse(self.Otp._otp_verify('signup', CODE, email='sita@example.com')[0], "Used up.")

    def test_email_only_when_sms_is_off(self):
        self.sms_on = False
        result = self._issue(email='sita@example.com', phone='9841234567')
        self.assertEqual(result['channels'], ['email'])
        self.assertFalse(self.texts)

    def test_sms_only_purpose(self):
        with patch.object(self.OtpClass, '_otp_policy', lambda self, purpose, company: {
            'channels': ('sms',), 'validity': timedelta(minutes=10)}):
            result = self._issue('checkout', email='sita@example.com', phone='9841234567')
            self.assertEqual(result['channels'], ['sms'])
            self.assertFalse(self.emails, "A phone check never emails the code.")
            self.sms_on = False
            result = self._issue('emi', phone='9801234567')
            self.assertIn("not available", result['error'])

    def test_wrong_codes_block(self):
        self._issue(email='sita@example.com')
        for left in (4, 3, 2, 1):
            record, error = self.Otp._otp_verify('signup', '000000', email='sita@example.com')
            self.assertIn(f'{left} tries left', error)
        record, error = self.Otp._otp_verify('signup', '000000', email='sita@example.com')
        self.assertIn('cannot be used any more', error)
        self.assertFalse(self.Otp._otp_verify('signup', CODE, email='sita@example.com')[0])

    def test_expiry_and_sms_cap(self):
        with patch.object(self.OtpClass, '_otp_policy', lambda self, purpose, company: {
            'channels': ('email', 'sms'), 'validity': timedelta(minutes=15)}), \
                patch.object(self.OtpClass, '_otp_sms_max_validity', lambda self, purpose, company: timedelta(minutes=10)):
            emailed = self._issue(email='a@example.com')['otp']
            both = self._issue(email='b@example.com', phone='9841234567')['otp']
        self.assertEqual(emailed._otp_minutes(), 15)
        self.assertEqual(both._otp_minutes(), 10, "The texted message says 10 minutes.")
        with patch.object(fields.Datetime, 'now', return_value=fields.Datetime.now() + timedelta(minutes=11)):
            record, error = self.Otp._otp_verify('signup', CODE, email='b@example.com')
        self.assertIn('expired', error)

    def test_cooldown_caps_and_replacement(self):
        self._issue(email='sita@example.com')
        self.assertIn('less than a minute ago', self._issue(email='sita@example.com')['error'])
        now = fields.Datetime.now()
        for minutes in (2, 4, 6, 8):
            with patch.object(fields.Datetime, 'now', return_value=now + timedelta(minutes=minutes)):
                self.assertFalse(self._issue(email='sita@example.com')['error'])
        with patch.object(fields.Datetime, 'now', return_value=now + timedelta(minutes=10)):
            self.assertIn('Too many codes', self._issue(email='sita@example.com')['error'])
        codes = self.Otp.search([('email', '=', 'sita@example.com')])
        self.assertEqual(codes.mapped('state').count('sent'), 1, "One live code at a time.")

    def test_site_wide_ceiling(self):
        self.env['ir.config_parameter'].sudo().set_param('auth_otp.max_per_hour', 2)
        self.assertFalse(self._issue(email='a@example.com')['error'])
        self.assertFalse(self._issue(email='b@example.com')['error'])
        self.assertIn('not available', self._issue(email='c@example.com')['error'])

    def test_link(self):
        with patch.object(otp_module, '_new_token', return_value='link-token'):
            result = self._issue(email='sita@example.com', with_link=True)
        self.assertEqual(result['token'], 'link-token')
        self.assertEqual(self.emails[0][2], 'link-token')
        record, error = self.Otp._otp_verify_link('signup', 'link-token')
        self.assertEqual(record, result['otp'])
        self.assertIn('not valid', self.Otp._otp_verify_link('signup', 'link-token')[1])
        self.assertIn('not valid', self.Otp._otp_verify_link('signup', 'other')[1])

    def test_partial_delivery(self):
        def fail_sms(otp, code):
            return False, "NestSMS down"
        with patch.object(self.OtpClass, '_otp_send_sms', fail_sms):
            result = self._issue(email='sita@example.com', phone='9841234567')
        self.assertEqual(result['channels'], ['email'], "Still usable by email.")
        self.assertIn('NestSMS down', result['otp'].failure_reason)

    def test_nothing_delivered(self):
        def boom(otp, code, token):
            raise OSError("SMTP down")
        result = self.Otp._otp_issue('signup', email='sita@example.com', email_sender=boom)
        self.assertIn("could not send", result['error'])
        self.assertEqual(self.Otp.search([('email', '=', 'sita@example.com')]).state, 'failed')

    def test_generic_email(self):
        result = self.Otp._otp_issue('email_login', email='sita@example.com')
        self.assertEqual(result['channels'], ['email'])
        mail = self.env['mail.mail'].sudo().search([('email_to', '=', 'sita@example.com')], limit=1)
        if mail:  # still queued in some setups; sent and deleted in others
            self.assertIn(CODE, mail.body_html)

    def test_proxy_ip_not_capped(self):
        self.assertFalse(self.Otp._is_public_ip('172.22.1.13'))
        self.assertFalse(self.Otp._is_public_ip(False))
        self.assertTrue(self.Otp._is_public_ip('103.10.28.5'))
