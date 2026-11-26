# Part of Odoo. See LICENSE file for full copyright and licensing details.

import requests

from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged

from odoo.addons.sms_nestsms.tools.sms_api import SmsApiNestSms, is_gsm7, looks_like_otp, nepal_mobile
from odoo.addons.sms_nestsms.tests.common import MESSAGE_ID, NestSmsCommon, fake_response


@tagged('post_install', '-at_install')
class TestNestSmsRules(NestSmsCommon):

    def test_nepal_mobile(self):
        for number, expected in [
            ('9841234567', '9841234567'),
            ('+977 984-1234567', '9841234567'),
            ('+9779801234567', '9801234567'),
            ('00977 9612345678', '9612345678'),
            ('977-9741234567', '9741234567'),
            ('+91 9812345678', False),     # India: same-looking digits, foreign route
            ('+1 555 123 4567', False),
            ('01-5970736', False),          # Kathmandu landline
            ('984123456', False),           # one digit short
            ('', False),
            (False, False),
        ]:
            self.assertEqual(nepal_mobile(number), expected, number)

    def test_looks_like_otp(self):
        for text in [
            "Flagship-Store: Your OTP for login is 456321",
            "Your verification code is 4821.",
            "Use 739201 as your one-time password",
            "Your code: 99812",
            "PIN 2211 for your account",
        ]:
            self.assertTrue(looks_like_otp(text), text)
        for text in [
            "Flagship-Store: Your order S00123 (Rs. 12345.00) is confirmed. Thank you!",
            "Flagship-Store: Your order S00042 is out for delivery. Please keep Rs. 25150.00 ready.",
            "Your tracking code is B79F9E65E673439.",
            "",
        ]:
            self.assertFalse(looks_like_otp(text), text)

    def test_is_gsm7(self):
        self.assertTrue(is_gsm7("Flagship-Store: Your order S00123 (Rs. 25000.00) is confirmed. Thank you!"))
        self.assertTrue(is_gsm7("Price: 10 EUR [approx.] {ok} ~ ^ | \\ \u20ac"))
        for text in ("order n\u00b0 S00123", "Rs. \u20a8 500", "\u0927\u0928\u094d\u092f\u0935\u093e\u0926", "\u2019smart quote\u2019"):
            self.assertFalse(is_gsm7(text), text)

    def test_brand_name_is_one_word(self):
        with self.assertRaises(ValidationError):
            self.company.sms_brand_name = "Flagship Store by Chaitanya Innovation"
        for bad in ("Flagship Store", "-Flagship", "Flagship-", "Flagship--Store", "Flagship_Store", "F"):
            with self.assertRaises(ValidationError, msg=bad):
                self.company.sms_brand_name = bad
        self.company.sms_brand_name = "Flagship-Store"
        self.company.sms_brand_name = "FlagshipStore"


@tagged('post_install', '-at_install')
class TestNestSmsApi(NestSmsCommon):

    def _batch(self, *numbers, content="Flagship-Store: Your order S00123 is confirmed."):
        sms_api = SmsApiNestSms(self.env)
        sms_api._set_company(self.company)
        return sms_api._send_sms_batch([{
            'content': content,
            'numbers': [{'uuid': f'uuid-{i}', 'number': number} for i, number in enumerate(numbers)],
        }])

    def test_send_success(self):
        [result] = self._batch('+977 984-1234567')
        self.assertEqual(result['state'], 'success')
        self.assertEqual(result['nestsms_message_id'], MESSAGE_ID)
        [call] = self.nestsms.calls
        self.assertEqual((call['method'], call['path']), ('POST', '/sms/send'))
        self.assertEqual(call['api_key'], 'nsms_live_test')
        self.assertEqual(call['payload'], {
            'to': '9841234567',
            'message': "Flagship-Store: Your order S00123 is confirmed.",
            'type': 'text',
            'message_type': 'transactional',
        })

    def test_non_gsm_text_goes_as_unicode(self):
        self._batch('9841234567', content="Flagship-Store: \u0927\u0928\u094d\u092f\u0935\u093e\u0926!")
        self.assertEqual(self.nestsms.calls[0]['payload']['type'], 'unicode')

    def test_send_success_top_level_message_id(self):
        self.nestsms.default = fake_response(200, {'success': True, 'message_id': 77})
        [result] = self._batch('9841234567')
        self.assertEqual(result['state'], 'success')
        self.assertEqual(result['nestsms_message_id'], '77')

    def test_foreign_number_never_leaves(self):
        [result] = self._batch('+91 9812345678')
        self.assertEqual(result['state'], 'nestsms_domestic_only')
        self.assertIn('domestic', result['failure_reason'])
        self.assertFalse(self.nestsms.calls)

    def test_otp_text_refused_before_nestsms(self):
        [result] = self._batch('9841234567', content="Flagship-Store: Your OTP for login is 456321")
        self.assertEqual(result['state'], 'nestsms_otp_template')
        self.assertFalse(self.nestsms.calls)

    def test_missing_api_key(self):
        self.company.sms_nestsms_api_key = False
        results = self._batch('9841234567', '9801234567')
        self.assertEqual([r['state'] for r in results], ['nestsms_account', 'nestsms_account'])
        self.assertIn('API key', results[0]['failure_reason'])
        self.assertFalse(self.nestsms.calls)

    def test_number_error_keeps_batch_going(self):
        self.nestsms.replies = [
            fake_response(400, {'success': False, 'error': "Invalid phone number format", 'code': 'INVALID_TO_FORMAT'}),
        ]
        results = self._batch('9841234567', '9801234567')
        self.assertEqual([r['state'] for r in results], ['wrong_number_format', 'success'])
        self.assertEqual(len(self.nestsms.calls), 2)

    def test_account_error_stops_batch(self):
        self.nestsms.replies = [
            fake_response(401, {'success': False, 'error': "Key not found or malformed", 'code': 'INVALID_API_KEY'}),
        ]
        results = self._batch('9841234567', '9801234567', '9861234567')
        self.assertEqual({r['state'] for r in results}, {'nestsms_account'})
        self.assertIn('INVALID_API_KEY', results[2]['failure_reason'])
        self.assertEqual(len(self.nestsms.calls), 1, "No more calls once the key is known to be bad.")

    def test_balance_error_maps_to_credit(self):
        self.nestsms.replies = [
            fake_response(400, {'success': False, 'error': "Wallet balance too low", 'code': 'INSUFFICIENT_BALANCE'}),
        ]
        [result] = self._batch('9841234567')
        self.assertEqual(result['state'], 'nestsms_balance')
        self.assertEqual(SmsApiNestSms.PROVIDER_TO_SMS_FAILURE_TYPE[result['state']], 'sms_credit')

    def test_rate_limit_stops_batch(self):
        self.nestsms.replies = [fake_response(429, {
            'success': False, 'error': "Too many requests", 'code': 'RATE_LIMIT_EXCEEDED',
            'message': "API key rate limit exceeded: 1000 requests per minute.", 'retry_after': 60,
        })]
        results = self._batch('9841234567', '9801234567')
        self.assertEqual([r['state'] for r in results], ['server_error', 'server_error'])
        self.assertIn('60', results[0]['failure_reason'])
        self.assertEqual(len(self.nestsms.calls), 1)

    def test_nestsms_otp_rejection(self):
        self.nestsms.replies = [fake_response(400, {
            'success': False, 'error': "Raw message looks like OTP content", 'code': 'OTP_CONTENT_REQUIRES_TEMPLATE',
        })]
        [result] = self._batch('9841234567')
        self.assertEqual(result['state'], 'nestsms_otp_template')

    def test_html_server_error(self):
        self.nestsms.replies = [fake_response(502, text="<html>Bad Gateway</html>")]
        results = self._batch('9841234567', '9801234567')
        self.assertEqual([r['state'] for r in results], ['server_error', 'server_error'])
        self.assertEqual(len(self.nestsms.calls), 1)

    def test_unreachable(self):
        self.nestsms.replies = [requests.exceptions.ConnectTimeout("timed out")]
        results = self._batch('9841234567', '9801234567')
        self.assertEqual([r['state'] for r in results], ['server_error', 'server_error'])
        self.assertEqual(len(self.nestsms.calls), 1)

    def test_every_state_has_a_failure_type(self):
        """Each state we return must map to a failure type that sms.sms and mail.notification
        both accept, or recording the failure would crash."""
        sms_types = dict(self.env['sms.sms']._fields['failure_type'].selection)
        notification_types = dict(self.env['mail.notification']._fields['failure_type'].selection)
        for state in set(SmsApiNestSms.ERROR_CODE_TO_STATE.values()) | {
            'nestsms_domestic_only', 'nestsms_otp_template', 'nestsms_rejected', 'server_error',
        }:
            failure_type = SmsApiNestSms.PROVIDER_TO_SMS_FAILURE_TYPE[state]
            self.assertIn(failure_type, sms_types, state)
            self.assertIn(failure_type, notification_types, state)


@tagged('post_install', '-at_install')
class TestNestSmsQueue(NestSmsCommon):

    def test_queue_goes_through_nestsms(self):
        self.customer._message_sms("Flagship-Store: Hello from the shop.", partner_ids=self.customer.ids, put_in_queue=True)
        sms = self.env['sms.sms'].search([('partner_id', '=', self.customer.id)])
        self.assertEqual(sms.state, 'outgoing')

        self._send_queue()

        self.assertEqual(len(self.nestsms.calls), 1)
        self.assertEqual(self.nestsms.calls[0]['payload']['to'], '9841234567')
        self.assertEqual(sms.state, 'pending')  # "Sent"
        self.assertEqual(sms.sms_tracker_id.sms_nestsms_message_id, MESSAGE_ID)

    def test_failure_reason_reaches_chatter(self):
        self.nestsms.replies = [
            fake_response(400, {'success': False, 'error': "Wallet balance too low", 'code': 'INSUFFICIENT_BALANCE'}),
        ]
        message = self.customer._message_sms("Flagship-Store: Hello.", partner_ids=self.customer.ids, put_in_queue=True)
        self._send_queue()
        notification = message.notification_ids
        self.assertEqual(notification.notification_status, 'exception')
        self.assertEqual(notification.failure_type, 'sms_credit')
        self.assertIn('Wallet balance too low', notification.failure_reason)


@tagged('post_install', '-at_install')
class TestNestSmsNotify(NestSmsCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.template = cls.env['sms.template'].create({
            'name': "Test notice",
            'model_id': cls.env['ir.model']._get_id('res.partner'),
            'body': "Flagship-Store: Hello {{ object.name }}.",
        })

    def _queued(self):
        return self.env['sms.sms'].search([('partner_id', '=', self.customer.id)])

    def test_notify_queues_sms(self):
        self.assertTrue(self.customer._sms_nestsms_notify(self.template, self.customer))
        sms = self._queued()
        self.assertEqual(sms.number, '+9779841234567')
        self.assertEqual(sms.body, "Flagship-Store: Hello Sita Gurung.")
        self.assertEqual(sms.state, 'outgoing')
        self.assertFalse(self.nestsms.calls, "Queued, not sent inside the business transaction.")
        self.assertEqual(sms.mail_message_id.author_id, self.env.ref('base.partner_root'))

    def test_notify_skips_without_key(self):
        self.company.sms_nestsms_api_key = False
        self.assertFalse(self.customer._sms_nestsms_notify(self.template, self.customer))
        self.assertFalse(self._queued())

    def test_notify_skips_foreign_number(self):
        self.customer.write({'phone': '+91 9812345678', 'country_id': self.env.ref('base.in').id})
        self.assertFalse(self.customer._sms_nestsms_notify(self.template, self.customer))
        self.assertFalse(self._queued())

    def test_notify_respects_opt_out(self):
        self.env['phone.blacklist'].sudo().add('+9779841234567')
        self.assertFalse(self.customer._sms_nestsms_notify(self.template, self.customer))
        self.assertFalse(self._queued())

    def test_notify_missing_template(self):
        self.assertFalse(self.customer._sms_nestsms_notify('sms_nestsms.no_such_template', self.customer))


@tagged('post_install', '-at_install')
class TestNestSmsTestWizard(NestSmsCommon):

    def test_wizard_sends(self):
        wizard = self.env['sms.nestsms.test'].create({'number': '9841234567'})
        self.assertEqual(wizard.body, "Flagship-Store: Test message from Odoo. Texts to customers now go out through NestSMS.")
        action = wizard.action_send()
        self.assertEqual(action['params']['type'], 'success')
        self.assertIn(MESSAGE_ID, action['params']['message'])

    def test_wizard_shows_refusal(self):
        self.nestsms.replies = [
            fake_response(403, {'success': False, 'error': "Request from a non-whitelisted IP", 'code': 'IP_RESTRICTED'}),
        ]
        wizard = self.env['sms.nestsms.test'].create({'number': '9841234567'})
        with self.assertRaisesRegex(UserError, 'non-whitelisted IP'):
            wizard.action_send()
