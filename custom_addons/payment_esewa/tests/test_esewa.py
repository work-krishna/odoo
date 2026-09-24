# Part of Odoo. See LICENSE file for full copyright and licensing details.

import base64
import json
from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.tests import tagged

from odoo.addons.payment.tests.common import PaymentCommon
from odoo.addons.payment.tests.http_common import PaymentHttpCommon
from odoo.addons.payment_esewa import const
from odoo.addons.payment_esewa.controllers.main import EsewaController

SEND = 'odoo.addons.payment.models.payment_provider.PaymentProvider._send_api_request'


class EsewaCommon(PaymentCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.esewa = cls._prepare_provider('esewa', update_values={
            'esewa_product_code': const.TEST_PRODUCT_CODE,
            'esewa_secret_key': const.TEST_SECRET_KEY,
        })
        cls.provider = cls.esewa
        cls.currency = cls._enable_currency('NPR')
        cls.amount = 1000.0

    def _signed_return(self, tx, **overrides):
        data = {
            'transaction_code': '000AWEO', 'status': 'COMPLETE', 'total_amount': 1000.0,
            'transaction_uuid': tx._esewa_get_transaction_uuid(), 'product_code': const.TEST_PRODUCT_CODE,
            'signed_field_names': 'transaction_code,status,total_amount,transaction_uuid,product_code,signed_field_names',
        }
        data.update(overrides)
        fields = data['signed_field_names'].split(',')
        data['signature'] = tx._esewa_sign(const.TEST_SECRET_KEY, fields, data)
        return data


@tagged('post_install', '-at_install')
class TestEsewa(EsewaCommon):

    def test_signature_matches_esewa_documentation(self):
        """ The success-redirect example from eSewa's ePay v2 documentation. """
        data = {
            'transaction_code': '000AWEO', 'status': 'COMPLETE', 'total_amount': 1000.0,
            'transaction_uuid': '250610-162413', 'product_code': 'EPAYTEST',
            'signed_field_names': 'transaction_code,status,total_amount,transaction_uuid,product_code,signed_field_names',
        }
        signature = self.env['payment.transaction']._esewa_sign(
            const.TEST_SECRET_KEY, data['signed_field_names'].split(','), data,
        )
        self.assertEqual(signature, '62GcfZTmVkzhtUeh+QJ1AqiJrjoWWGof3U+eTPTZ7fA=')

    def test_rendering_values_are_signed(self):
        tx = self._create_transaction('redirect', reference='S00042/1')
        values = tx._get_specific_rendering_values(None)
        form = values['esewa_values']
        self.assertEqual(values['api_url'], const.FORM_URLS['test'])
        self.assertEqual(form['transaction_uuid'], 'S00042-1')  # only letters, digits, hyphens
        self.assertEqual(form['total_amount'], '1000')
        self.assertEqual(form['signed_field_names'], 'total_amount,transaction_uuid,product_code')
        self.assertEqual(form['signature'], tx._esewa_sign(
            const.TEST_SECRET_KEY, const.REQUEST_SIGNED_FIELDS, form,
        ))
        self.assertTrue(form['success_url'].endswith(EsewaController._return_url))

    def test_status_complete_marks_done(self):
        tx = self._create_transaction('redirect')
        status = {'product_code': 'EPAYTEST', 'transaction_uuid': tx._esewa_get_transaction_uuid(),
                  'total_amount': 1000.0, 'status': 'COMPLETE', 'ref_id': '0001TS9'}
        with patch(SEND, return_value=status):
            tx._esewa_sync_status()
        self.assertEqual(tx.state, 'done')
        self.assertEqual(tx.provider_reference, '0001TS9')

    def test_amount_mismatch_is_rejected(self):
        tx = self._create_transaction('redirect')
        status = {'transaction_uuid': tx._esewa_get_transaction_uuid(), 'total_amount': 10.0,
                  'status': 'COMPLETE', 'ref_id': 'X'}
        with patch(SEND, return_value=status):
            tx._esewa_sync_status()
        self.assertEqual(tx.state, 'error')

    def test_statuses(self):
        for status, state in (('PENDING', 'pending'), ('CANCELED', 'cancel'), ('NOT_FOUND', 'cancel')):
            tx = self._create_transaction('redirect', reference=f'ref-{status}')
            payload = {'transaction_uuid': tx._esewa_get_transaction_uuid(), 'total_amount': 1000.0,
                       'status': status}
            with patch(SEND, return_value=payload):
                tx._esewa_sync_status()
            self.assertEqual(tx.state, state, status)

    def test_tampered_signature_detected(self):
        tx = self._create_transaction('redirect')
        data = self._signed_return(tx)
        self.assertTrue(tx._esewa_verify_signature(data))
        data['total_amount'] = 1.0
        self.assertFalse(tx._esewa_verify_signature(data))
        self.assertFalse(tx._esewa_verify_signature(dict(data, signature='')))

    def test_cron_settles_abandoned_payments(self):
        tx = self._create_transaction('redirect', state='pending')
        tx._esewa_get_transaction_uuid()
        # Odoo stores UTC; PostgreSQL's now() would use the server's time zone.
        an_hour_ago = fields.Datetime.now() - timedelta(hours=1)
        self.env.cr.execute("UPDATE payment_transaction SET create_date = %s WHERE id = %s", [an_hour_ago, tx.id])
        tx.invalidate_recordset(['create_date'])
        status = {'transaction_uuid': tx.esewa_transaction_uuid, 'total_amount': 1000.0, 'status': 'COMPLETE'}
        with patch(SEND, return_value=status):
            self.env['payment.transaction']._esewa_cron_check_pending()
        self.assertEqual(tx.state, 'done')


@tagged('post_install', '-at_install')
class TestEsewaHttp(EsewaCommon, PaymentHttpCommon):

    def test_return_route_confirms_with_status_api(self):
        tx = self._create_transaction('redirect')
        encoded = base64.b64encode(json.dumps(self._signed_return(tx)).encode()).decode()
        status = {'transaction_uuid': tx.esewa_transaction_uuid, 'total_amount': 1000.0,
                  'status': 'COMPLETE', 'ref_id': 'R1'}
        with patch(SEND, return_value=status) as send:
            self._make_http_get_request(self._build_url(EsewaController._return_url), params={'data': encoded})
        send.assert_called_once()
        self.assertEqual(tx.state, 'done')

    def test_return_route_ignores_forged_data(self):
        tx = self._create_transaction('redirect')
        forged = dict(self._signed_return(tx), signature='forged')
        encoded = base64.b64encode(json.dumps(forged).encode()).decode()
        with patch(SEND) as send:
            self._make_http_get_request(self._build_url(EsewaController._return_url), params={'data': encoded})
        send.assert_not_called()
        self.assertEqual(tx.state, 'draft')

    def test_failure_route_cancels(self):
        tx = self._create_transaction('redirect')
        uuid = tx._esewa_get_transaction_uuid()
        with patch(SEND, return_value={'transaction_uuid': uuid, 'total_amount': 1000.0, 'status': 'NOT_FOUND'}):
            self._make_http_get_request(self._build_url(EsewaController._failure_url), params={'uuid': uuid})
        self.assertEqual(tx.state, 'cancel')
