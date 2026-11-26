# Part of Odoo. See LICENSE file for full copyright and licensing details.

import json
from unittest.mock import patch

import requests

from odoo.tests import TransactionCase

from odoo.addons.sms.tools.sms_api import SmsApi
from odoo.addons.sms_nestsms.tools.sms_api import SmsApiNestSms


def fake_response(status, data=None, text=None):
    response = requests.Response()
    response.status_code = status
    response.url = 'https://auth.nestsms.com/api/v1/sms/send'
    if text is None:
        text = json.dumps(data)
        response.headers['Content-Type'] = 'application/json'
    response._content = text.encode()
    response.encoding = 'utf-8'
    return response


MESSAGE_ID = '5d7e5d4a-a0fd-4f15-b13f-8d7f183f2dd7'
TEMPLATE_ID = '550e8400-e29b-41d4-a716-446655440000'


def sent_reply(message_id=MESSAGE_ID):
    """NestSMS's answer to a single send, as documented."""
    return fake_response(200, {'success': True, 'message': "SMS queued successfully", 'data': {
        'message_id': message_id, 'batch_id': 'd09b8f7c-4f4c-4df6-99ab-6fc88a2f1bd9', 'job_id': 'job-uuid-here',
        'cost': 1.0, 'remaining_balance': 499.0, 'recipient': '9841234567',
    }})


class FakeNestSms:
    """Stands in for `SmsApiNestSms._nestsms_request`: records each call and answers from a
    list of canned replies, then with `default`."""

    def __init__(self):
        self.calls = []
        self.replies = []
        self.default = sent_reply()

    def __call__(self, session, api_key, method, path, payload=None):
        self.calls.append({'api_key': api_key, 'method': method, 'path': path, 'payload': payload})
        reply = self.replies.pop(0) if self.replies else self.default
        if isinstance(reply, Exception):
            raise reply
        return reply


def patch_nestsms(test_case):
    """Replace the NestSMS HTTP call with a FakeNestSms for this test; returns it. Anything
    reaching Odoo IAP (an international route) fails the test."""
    fake = FakeNestSms()
    test_case.startPatcher(patch.object(SmsApiNestSms, '_nestsms_request', side_effect=fake))
    test_case.startPatcher(patch.object(SmsApi, '_send_sms_batch', side_effect=AssertionError("SMS sent through Odoo IAP")))
    return fake


def send_sms_queue(env):
    """Send queued SMS like the cron does, minus its commits."""
    env['sms.sms'].search([('state', '=', 'outgoing')]).send(unlink_sent=False)


class NestSmsCommon(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.company.write({
            'sms_nestsms_api_key': 'nsms_live_test',
            'sms_brand_name': 'Flagship-Store',
            'country_id': cls.env.ref('base.np').id,
        })
        cls.customer = cls.env['res.partner'].create({
            'name': 'Sita Gurung',
            'phone': '+977 984-1234567',
            'country_id': cls.env.ref('base.np').id,
        })

    def setUp(self):
        super().setUp()
        self.nestsms = patch_nestsms(self)

    def _send_queue(self):
        send_sms_queue(self.env)
