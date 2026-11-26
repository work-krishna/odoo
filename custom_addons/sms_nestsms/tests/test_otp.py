# Part of Odoo. See LICENSE file for full copyright and licensing details.

from datetime import timedelta

from freezegun import freeze_time

from odoo import fields
from odoo.tests import tagged

from odoo.addons.sms_nestsms.tests.common import (
    MESSAGE_ID, TEMPLATE_ID, NestSmsCommon, approve_otp, fake_response, sent_reply,
)

OTP_TEXT = "Flagship-Store: Your OTP for login is {otp}. It is valid for 10 minutes. Never share this code with anyone."


@tagged('post_install', '-at_install')
class TestOtp(NestSmsCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        approve_otp(cls.company, 'login')
        cls.Otp = cls.env['sms.nestsms.otp']

    def _sent_code(self):
        """The code in the last template send."""
        return self.nestsms.calls[-1]['payload']['variables']['otp']

    def test_send_and_verify(self):
        otp, error = self.Otp._nestsms_send('login', '+977 984-1234567')
        self.assertFalse(error)
        [call] = self.nestsms.calls
        self.assertEqual(call['payload']['to'], '9841234567')
        self.assertEqual(call['payload']['template_id'], TEMPLATE_ID)
        self.assertEqual(call['payload']['message_type'], 'otp')
        self.assertNotIn('message', call['payload'], "OTPs never go as raw text.")
        code = self._sent_code()
        self.assertRegex(code, r'^\d{6}$')
        self.assertEqual(otp.nestsms_message_id, MESSAGE_ID)
        self.assertNotIn(code, otp.sudo().code_hash)

        record, error = self.Otp._nestsms_verify('login', '9841234567', f" {code[:3]} {code[3:]} ")
        self.assertEqual(record, otp)
        self.assertFalse(error)
        self.assertEqual(otp.state, 'verified')
        # Used up.
        record, error = self.Otp._nestsms_verify('login', '9841234567', code)
        self.assertFalse(record)

    def test_wrong_codes_block(self):
        self.Otp._nestsms_send('login', '9841234567')
        code = self._sent_code()
        wrong = '000000' if code != '000000' else '111111'
        for left in (4, 3, 2, 1):
            record, error = self.Otp._nestsms_verify('login', '9841234567', wrong)
            self.assertFalse(record)
            self.assertIn(f"{left} tries left", error)
        record, error = self.Otp._nestsms_verify('login', '9841234567', wrong)
        self.assertIn("can no longer be used", error)
        # Even the right code is dead now.
        record, error = self.Otp._nestsms_verify('login', '9841234567', code)
        self.assertFalse(record)

    def test_code_is_per_purpose(self):
        approve_otp(self.company, 'checkout')
        self.Otp._nestsms_send('login', '9841234567')
        record, error = self.Otp._nestsms_verify('checkout', '9841234567', self._sent_code())
        self.assertFalse(record)

    def test_expiry(self):
        self.Otp._nestsms_send('login', '9841234567')
        code = self._sent_code()
        with freeze_time(fields.Datetime.now() + timedelta(minutes=11)):
            record, error = self.Otp._nestsms_verify('login', '9841234567', code)
        self.assertFalse(record)
        self.assertIn("expired", error)

    def test_new_code_replaces_old(self):
        self.Otp._nestsms_send('login', '9841234567')
        first = self._sent_code()
        with freeze_time(fields.Datetime.now() + timedelta(seconds=61)):
            self.Otp._nestsms_send('login', '9841234567')
        second = self._sent_code()
        if first != second:
            self.assertFalse(self.Otp._nestsms_verify('login', '9841234567', first)[0])
        self.assertTrue(self.Otp._nestsms_verify('login', '9841234567', second)[0])

    def test_resend_cooldown_and_hourly_cap(self):
        self.Otp._nestsms_send('login', '9841234567')
        otp, error = self.Otp._nestsms_send('login', '9841234567')
        self.assertFalse(otp)
        self.assertIn("wait a minute", error)
        self.assertEqual(len(self.nestsms.calls), 1)

        now = fields.Datetime.now()
        for minutes in (2, 4, 6, 8):
            with freeze_time(now + timedelta(minutes=minutes)):
                self.assertTrue(self.Otp._nestsms_send('login', '9841234567')[0])
        with freeze_time(now + timedelta(minutes=10)):
            otp, error = self.Otp._nestsms_send('login', '9841234567')
        self.assertFalse(otp)
        self.assertIn("Too many codes", error)
        self.assertEqual(len(self.nestsms.calls), 5)

    def test_site_wide_ceiling(self):
        self.env['ir.config_parameter'].sudo().set_param('sms_nestsms.otp_max_per_hour', 2)
        self.assertTrue(self.Otp._nestsms_send('login', '9841234567')[0])
        self.assertTrue(self.Otp._nestsms_send('login', '9801234567')[0])
        otp, error = self.Otp._nestsms_send('login', '9861234567')
        self.assertFalse(otp)
        self.assertEqual(len(self.nestsms.calls), 2)

    def test_proxy_ip_not_capped(self):
        Otp = self.Otp
        self.assertFalse(Otp._is_public_ip('172.22.1.13'))
        self.assertFalse(Otp._is_public_ip('127.0.0.1'))
        self.assertFalse(Otp._is_public_ip(False))
        self.assertTrue(Otp._is_public_ip('103.10.28.5'))

    def test_refusals(self):
        otp, error = self.Otp._nestsms_send('login', '+91 9812345678')
        self.assertIn("Nepali mobile", error)
        self.company.sms_otp_signup = False
        otp, error = self.Otp._nestsms_send('signup', '9841234567')  # switched off
        self.assertIn("not available", error)
        self.assertFalse(self.nestsms.calls)

    def test_nestsms_refusal_is_recorded(self):
        self.nestsms.replies = [fake_response(400, {
            'success': False, 'error': "Missing template variables", 'code': 'TEMPLATE_VARIABLES_MISSING',
            'missing_variables': ['otp'],
        })]
        otp, error = self.Otp._nestsms_send('login', '9841234567')
        self.assertFalse(otp)
        self.assertIn("could not send", error)
        failed = self.Otp.search([('number', '=', '9841234567')])
        self.assertEqual(failed.state, 'failed')
        self.assertIn('TEMPLATE_VARIABLES_MISSING', failed.failure_reason)
        # The template is unusable: the flow stops instead of failing for every customer.
        self.assertFalse(self.company._sms_otp_enabled('login'))
        otp, error = self.Otp._nestsms_send('login', '9801234567')
        self.assertIn("not available", error)
        self.assertEqual(len(self.nestsms.calls), 1, "No second attempt with a rejected template.")

    def test_passing_errors_keep_the_flow_on(self):
        self.nestsms.replies = [fake_response(400, {
            'success': False, 'error': "Wallet balance too low", 'code': 'INSUFFICIENT_BALANCE',
        })]
        self.assertFalse(self.Otp._nestsms_send('login', '9841234567')[0])
        self.assertTrue(self.company._sms_otp_enabled('login'), "Not a template problem: no reason to stop.")

    def test_unapproved_template_never_sends(self):
        self.company.sms_otp_login_template = '11111111-2222-3333-4444-555555555555'  # edited after Check
        self.assertFalse(self.company._sms_otp_enabled('login'))
        otp, error = self.Otp._nestsms_send('login', '9841234567')
        self.assertIn("not available", error)
        self.assertFalse(self.nestsms.calls)


@tagged('post_install', '-at_install')
class TestOtpTemplateCheck(NestSmsCommon):

    def _template_reply(self, **values):
        template = {
            'id': TEMPLATE_ID, 'name': "Login", 'message_type': 'otp', 'content': OTP_TEXT,
            'is_active': True, 'is_verified': True, **values,
        }
        return fake_response(200, {'success': True, 'template': template})

    def _check(self, **values):
        self.company.sms_otp_login_template = TEMPLATE_ID
        self.nestsms.replies = [self._template_reply(**values)]
        return self.company._sms_otp_check_template('login')

    def test_good_template(self):
        content, problems = self._check()
        self.assertEqual(problems, [])
        self.assertEqual(content, OTP_TEXT)
        self.assertEqual(self.nestsms.calls[0]['method'], 'GET')
        self.assertEqual(self.nestsms.calls[0]['path'], f'/sms/templates/{TEMPLATE_ID}')

    def test_problems(self):
        _content, problems = self._check(
            is_verified=False, message_type='transactional',
            content="FlagshipStore: Hi {name}, your code is {otp}. Valid for 5 minutes.",
        )
        text = ' '.join(problems)
        self.assertIn("not approved", text)
        self.assertIn("must be OTP", text)
        self.assertIn("{name}", text)
        self.assertIn('start with "Flagship-Store:"', text)
        self.assertIn("5 minutes", text)

    def _choose_and_send(self, content):
        """Approve a template with `content` through Check, then text a login code; returns
        the variables sent to NestSMS."""
        self.company.write({'sms_otp_login': True, 'sms_otp_login_template': TEMPLATE_ID})
        self.nestsms.replies = [self._template_reply(content=content)]
        action = self.env['res.config.settings'].create({}).with_context(
            sms_otp_purpose='login').action_sms_otp_check_template()
        self.assertEqual(action['params']['type'], 'success', action['params']['message'])
        self.env['sms.nestsms.otp']._nestsms_send('login', '9841234567')
        return self.nestsms.calls[-1]['payload']['variables']

    def test_placeholders_are_filled(self):
        """A template like NestSMS's own examples: brand, purpose and expiry as variables."""
        variables = self._choose_and_send(
            "{companyName}: Your OTP for {purpose} is {otp}. It is valid for {expiry} minutes. Never share it.")
        self.assertEqual(set(variables), {'companyName', 'purpose', 'otp', 'expiry'}, "Exactly the declared ones.")
        self.assertEqual(variables['companyName'], 'Flagship-Store')
        self.assertEqual(variables['purpose'], 'login')
        self.assertEqual(variables['expiry'], '10')
        self.assertRegex(variables['otp'], r'^\d{6}$')

    def test_bare_expiry_gets_its_unit(self):
        variables = self._choose_and_send("{app_name}: Your code is {otp}. It expires in {expiry}.")
        self.assertEqual(variables['expiry'], '10 minutes')
        self.assertEqual(variables['app_name'], 'Flagship-Store')

    def test_unfillable_placeholder_blocks_approval(self):
        _content, problems = self._check(content="{companyName}: Hi {customer}, your OTP is {otp}.")
        self.assertEqual(len(problems), 1)
        self.assertIn('{customer}', problems[0])

    def test_prefix_checked_on_filled_text(self):
        self.company.sms_brand_name = 'FlagshipStore'
        _content, problems = self._check(content="{companyName}: Your OTP is {otp}. Valid for {expiry} minutes.")
        self.assertEqual(problems, [])
        _content, problems = self._check(content="Hello from {companyName}: your OTP is {otp}.")
        self.assertIn('start with "FlagshipStore:"', ' '.join(problems))

    def test_check_button_approves(self):
        self.company.write({'sms_otp_login': True, 'sms_otp_login_template': TEMPLATE_ID})
        self.assertFalse(self.company._sms_otp_enabled('login'), "Off until checked.")
        self.nestsms.replies = [self._template_reply()]
        settings = self.env['res.config.settings'].create({})
        self.assertFalse(settings.sms_otp_login_approved)
        action = settings.with_context(sms_otp_purpose='login').action_sms_otp_check_template()
        self.assertEqual(action['params']['type'], 'success')
        self.assertTrue(self.company._sms_otp_enabled('login'))
        self.assertTrue(self.env['res.config.settings'].create({}).sms_otp_login_approved)

    def test_check_button_withdraws_approval(self):
        approve_otp(self.company, 'login')
        self.nestsms.replies = [self._template_reply(is_verified=False)]
        settings = self.env['res.config.settings'].create({})
        action = settings.with_context(sms_otp_purpose='login').action_sms_otp_check_template()
        self.assertEqual(action['params']['type'], 'warning')
        self.assertIn("stay off", action['params']['message'])
        self.assertFalse(self.company._sms_otp_enabled('login'))

    def test_balance_button(self):
        self.nestsms.replies = [fake_response(200, {'success': True, 'data': {
            'balance': 500.0, 'currency': 'NPR', 'per_message_cost': 1.0, 'messages_remaining': 500,
        }})]
        action = self.env['res.config.settings'].create({}).action_sms_nestsms_balance()
        self.assertIn("NPR 500.0", action['params']['message'])
        self.assertEqual(self.nestsms.calls[0]['path'], '/sms/balance')


@tagged('post_install', '-at_install')
class TestDeliveryStatus(NestSmsCommon):

    def _sent_message(self, message_id):
        self.nestsms.replies = [sent_reply(message_id)]
        message = self.customer._message_sms("Flagship-Store: Hello.", partner_ids=self.customer.ids, put_in_queue=True)
        self._send_queue()
        self.assertEqual(message.notification_ids.notification_status, 'pending')
        return message

    def _status_reply(self, status, **values):
        return fake_response(200, {'success': True, 'type': 'single', 'data': {
            'message_id': MESSAGE_ID, 'status': status, 'recipient': '9841234567', **values,
        }})

    def test_delivered(self):
        message = self._sent_message(MESSAGE_ID)
        self.nestsms.replies = [self._status_reply('delivered')]
        self.env['sms.tracker']._nestsms_cron_update_delivery()
        self.assertEqual(self.nestsms.calls[-1]['path'], f'/sms/status/{MESSAGE_ID}')
        self.assertEqual(message.notification_ids.notification_status, 'sent')  # "Delivered"

    def test_failed(self):
        message = self._sent_message(MESSAGE_ID)
        self.nestsms.replies = [self._status_reply('failed', error_code='E21', error_message="Handset unreachable")]
        self.env['sms.tracker']._nestsms_cron_update_delivery()
        notification = message.notification_ids
        self.assertEqual(notification.notification_status, 'exception')
        self.assertEqual(notification.failure_type, 'sms_not_delivered')
        self.assertEqual(notification.failure_reason, "Handset unreachable")

    def test_still_on_its_way(self):
        message = self._sent_message(MESSAGE_ID)
        self.nestsms.replies = [self._status_reply('sent')]
        self.env['sms.tracker']._nestsms_cron_update_delivery()
        self.assertEqual(message.notification_ids.notification_status, 'pending')

    def test_old_texts_left_alone(self):
        self._sent_message(MESSAGE_ID)
        calls = len(self.nestsms.calls)
        with freeze_time(fields.Datetime.now() + timedelta(days=3)):
            self.env['sms.tracker']._nestsms_cron_update_delivery()
        self.assertEqual(len(self.nestsms.calls), calls)
