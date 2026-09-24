# Part of Odoo. See LICENSE file for full copyright and licensing details.

import json
from unittest.mock import patch

import requests

from odoo.exceptions import ValidationError
from odoo.tests import tagged

from odoo.addons.payment.tests.common import PaymentCommon
from odoo.addons.payment.tests.http_common import PaymentHttpCommon
from odoo.addons.payment_khalti import const
from odoo.addons.payment_khalti.controllers.main import KhaltiController

SEND = 'odoo.addons.payment.models.payment_provider.PaymentProvider._send_api_request'
POST = 'odoo.addons.payment_khalti.models.payment_transaction.requests.post'


def FakeResponse(status_code, data):
    response = requests.Response()
    response.status_code = status_code
    response.reason = 'OK' if status_code == 200 else 'Bad Request'
    response.url = 'https://dev.khalti.com/api/v2/epayment/lookup/'
    response.headers['Content-Type'] = 'application/json'
    response._content = json.dumps(data).encode()
    return response


class KhaltiCommon(PaymentCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.khalti = cls._prepare_provider('khalti', update_values={'khalti_secret_key': 'test_secret'})
        cls.provider = cls.khalti
        cls.currency = cls._enable_currency('NPR')
        cls.amount = 1300.0
        cls.initiate_response = {
            'pidx': 'bZQLD9wRVWo4CdESSfuSsB',
            'payment_url': 'https://test-pay.khalti.com/?pidx=bZQLD9wRVWo4CdESSfuSsB',
            'expires_at': '2023-05-25T16:26:16.471649+05:45', 'expires_in': 1800,
        }

    def _initiated_tx(self, **values):
        tx = self._create_transaction('redirect', **values)
        with patch(SEND, return_value=self.initiate_response):
            rendering = tx._get_specific_rendering_values(None)
        return tx, rendering


@tagged('post_install', '-at_install')
class TestKhalti(KhaltiCommon):

    def test_initiate_request_and_redirect(self):
        tx = self._create_transaction('redirect')
        with patch(SEND, return_value=self.initiate_response) as send:
            rendering = tx._get_specific_rendering_values(None)
        payload = send.call_args.kwargs['json']
        self.assertEqual(payload['amount'], 130000)  # paisa
        self.assertEqual(payload['purchase_order_id'], tx.reference)
        self.assertTrue(payload['return_url'].endswith(KhaltiController._return_url))
        self.assertEqual(tx.khalti_pidx, 'bZQLD9wRVWo4CdESSfuSsB')
        self.assertEqual(rendering['api_url'], 'https://test-pay.khalti.com/')
        self.assertEqual(rendering['khalti_params'], {'pidx': 'bZQLD9wRVWo4CdESSfuSsB'})

    def test_auth_header_and_urls(self):
        self.assertEqual(self.khalti._build_request_headers('POST', 'x', {}), {'Authorization': 'Key test_secret'})
        self.assertEqual(self.khalti._build_request_url(const.LOOKUP_ENDPOINT),
                         'https://dev.khalti.com/api/v2/epayment/lookup/')

    def test_initiate_error_sets_error(self):
        tx = self._create_transaction('redirect')
        with patch(SEND, side_effect=ValidationError("amount: Amount should be greater than Rs. 10")):
            self.assertEqual(tx._get_specific_rendering_values(None), {})
        self.assertEqual(tx.state, 'error')

    def test_lookup_completed(self):
        tx, _rendering = self._initiated_tx()
        lookup = {'pidx': tx.khalti_pidx, 'total_amount': 130000, 'status': 'Completed',
                  'transaction_id': 'GFq9PFS7b2iYvL8Lir9oXe', 'fee': 0, 'refunded': False}
        with patch(POST, return_value=FakeResponse(200, lookup)):
            tx._khalti_sync_status()
        self.assertEqual(tx.state, 'done')
        self.assertEqual(tx.provider_reference, 'GFq9PFS7b2iYvL8Lir9oXe')

    def test_lookup_expired_and_canceled_come_with_400(self):
        for status in ('Expired', 'User canceled'):
            tx, _rendering = self._initiated_tx(reference=f'tx-{status}')
            with patch(POST, return_value=FakeResponse(400, {'pidx': tx.khalti_pidx, 'total_amount': 130000,
                                                             'status': status, 'transaction_id': None,
                                                             'fee': 0, 'refunded': False})):
                tx._khalti_sync_status()
            self.assertEqual(tx.state, 'cancel', status)

    def test_lookup_pending_and_refunded(self):
        tx, _r = self._initiated_tx(reference='tx-pending')
        with patch(POST, return_value=FakeResponse(200, {'pidx': tx.khalti_pidx, 'status': 'Pending',
                                                         'total_amount': 130000})):
            tx._khalti_sync_status()
        self.assertEqual(tx.state, 'pending')
        tx, _r = self._initiated_tx(reference='tx-refunded')
        with patch(POST, return_value=FakeResponse(200, {'pidx': tx.khalti_pidx, 'status': 'Refunded',
                                                         'total_amount': 130000})):
            tx._khalti_sync_status()
        self.assertEqual(tx.state, 'error')

    def test_amount_mismatch_rejected(self):
        tx, _r = self._initiated_tx()
        with patch(POST, return_value=FakeResponse(200, {'pidx': tx.khalti_pidx, 'status': 'Completed',
                                                         'total_amount': 1000})):
            tx._khalti_sync_status()
        self.assertEqual(tx.state, 'error')

    def test_lookup_failure_leaves_transaction(self):
        tx, _r = self._initiated_tx()
        with patch(POST, return_value=FakeResponse(500, {'detail': 'down'})):
            tx._khalti_sync_status()
        self.assertEqual(tx.state, 'draft')


@tagged('post_install', '-at_install')
class TestKhaltiHttp(KhaltiCommon, PaymentHttpCommon):

    def test_return_route_trusts_only_lookup(self):
        tx, _r = self._initiated_tx()
        # The query string claims success, but lookup says the payment was canceled.
        params = {'pidx': tx.khalti_pidx, 'status': 'Completed', 'amount': '130000',
                  'purchase_order_id': tx.reference}
        with patch(POST, return_value=FakeResponse(400, {'pidx': tx.khalti_pidx, 'status': 'User canceled',
                                                         'total_amount': 130000})):
            self._make_http_get_request(self._build_url(KhaltiController._return_url), params=params)
        self.assertEqual(tx.state, 'cancel')
