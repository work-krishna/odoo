# Part of Odoo. See LICENSE file for full copyright and licensing details.

from unittest.mock import patch

import requests

from odoo.tests import BaseCase, tagged

from odoo.addons.delivery_ncm import const
from odoo.addons.delivery_ncm.models.ncm_request import NcmClient, NcmError
from odoo.addons.delivery_ncm.tests.common import CLIENT_HTTP, THROTTLE, FakeNcm, fake_response

# What NCM's demo server answered for an unknown branch (Django debug page, trimmed).
DJANGO_DEBUG_TEXT = """DoesNotExist at /api/v1/shipping-rate
Branch matching query does not exist.

Request Method: GET
Django Version: 2.2.5
SECRET_KEY = '********************'
DATABASES = {'default': {'NAME': 'ncm2', 'USER': 'root'}}
"""


@tagged('post_install', '-at_install')
class TestNcmRequest(BaseCase):

    def setUp(self):
        super().setUp()
        self.fake = FakeNcm()
        self.startPatcher(patch(CLIENT_HTTP, side_effect=self.fake))
        self.startPatcher(patch(THROTTLE))
        self.client = NcmClient(const.API_URLS['demo'], token='abc')

    def test_sends_token_and_parses_rate(self):
        self.fake.routes[('GET', '/api/v1/shipping-rate')] = fake_response(200, {'charge': '170.00'})
        self.assertEqual(self.client.get_rate('TINKUNE', 'POKHARA', 'Pickup/Collect'), 170.0)
        call = self.fake.calls[0]
        self.assertEqual(call['headers']['Authorization'], 'Token abc')
        self.assertEqual(call['params'], {'creation': 'TINKUNE', 'destination': 'POKHARA', 'type': 'Pickup/Collect'})

    def test_django_debug_page_is_summarized(self):
        self.fake.routes[('GET', '/api/v1/shipping-rate')] = fake_response(500, text=DJANGO_DEBUG_TEXT)
        with self.assertRaises(NcmError) as capture:
            self.client.get_rate('TINKUNE', 'NOWHERE', 'Pickup/Collect')
        message = capture.exception.message
        self.assertIn('HTTP 500', message)
        self.assertIn('Branch matching query does not exist', message)
        self.assertNotIn('DATABASES', message, "The debug page's settings must never be shown.")
        self.assertFalse(capture.exception.uncertain)

    def test_field_errors_are_joined(self):
        self.fake.routes[('POST', '/api/v1/order/create')] = fake_response(
            400, {'Error': {'phone': 'Invalid Phone Number', 'branch': 'Invalid Branch'}},
        )
        with self.assertRaises(NcmError) as capture:
            self.client.create_order({'name': 'x'})
        self.assertEqual(capture.exception.message, 'phone: Invalid Phone Number; branch: Invalid Branch')
        self.assertFalse(capture.exception.uncertain)

    def test_read_timeout_is_uncertain_connect_timeout_is_not(self):
        self.fake.routes[('POST', '/api/v1/order/create')] = requests.exceptions.ReadTimeout()
        with self.assertRaises(NcmError) as capture:
            self.client.create_order({})
        self.assertTrue(capture.exception.uncertain)

        self.fake.routes[('POST', '/api/v1/order/create')] = requests.exceptions.ConnectTimeout()
        with self.assertRaises(NcmError) as capture:
            self.client.create_order({})
        self.assertFalse(capture.exception.uncertain)

    def test_bulk_statuses(self):
        self.fake.routes[('POST', '/api/v1/orders/statuses')] = fake_response(200, {
            'result': {'4041': 'Pickup Order Created', '3841': 'Delivered'}, 'errors': [4042],
        })
        result, errors = self.client.get_statuses([4041, 3841, 4042])
        self.assertEqual(result['3841'], 'Delivered')
        self.assertEqual(errors, [4042])
        self.assertEqual(self.fake.calls[0]['json'], {'orders': [4041, 3841, 4042]})

    def test_status_mapping(self):
        cases = {
            'Pickup Order Created': 'created',
            'Drop off Order Created': 'created',
            'Sent for Pickup': 'pickup',
            'Pickup Complete': 'picked_up',
            'Arrived': 'in_transit',
            'In Transit': 'in_transit',
            'Sent for Delivery': 'out_for_delivery',
            'Delivered': 'delivered',
            'Sent to Vendor': 'returned',
            'Return in process': 'returning',
            'Order Cancelled': 'cancelled',
            'Hold - customer not reachable': 'exception',
            'Something new': 'unknown',
        }
        for status, state in cases.items():
            self.assertEqual(const.status_to_state(status), state, status)
