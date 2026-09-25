# Part of Odoo. See LICENSE file for full copyright and licensing details.

import base64
import json
from datetime import timedelta
from unittest.mock import patch

from psycopg2 import IntegrityError

from odoo import fields
from odoo.exceptions import ValidationError
from odoo.tests import tagged
from odoo.tools import mute_logger

from odoo.addons.payment.controllers.post_processing import PaymentPostProcessing
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
        self.assertRegex(form['transaction_uuid'], rf'^{tx.id}-[0-9a-f]{{12}}$')  # random, letters/digits/hyphens
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

    def _age(self, tx, **delta):
        # Odoo stores UTC; PostgreSQL's now() would use the server's time zone.
        self.env.cr.execute("UPDATE payment_transaction SET create_date = %s WHERE id = %s",
                            [fields.Datetime.now() - timedelta(**delta), tx.id])
        tx.invalidate_recordset(['create_date'])

    def test_statuses(self):
        for status, state in (('PENDING', 'pending'), ('CANCELED', 'cancel'), ('NOT_FOUND', 'draft')):
            tx = self._create_transaction('redirect', reference=f'ref-{status}')
            payload = {'transaction_uuid': tx._esewa_get_transaction_uuid(), 'total_amount': 1000.0,
                       'status': status}
            with patch(SEND, return_value=payload):
                tx._esewa_sync_status()
            self.assertEqual(tx.state, state, status)

    def test_not_found_cancels_only_after_the_payment_session(self):
        tx = self._create_transaction('redirect')
        payload = {'transaction_uuid': tx._esewa_get_transaction_uuid(), 'total_amount': 1000.0,
                   'status': 'NOT_FOUND'}
        self._age(tx, minutes=10)
        with patch(SEND, return_value=payload):
            tx._esewa_sync_status()
        self.assertEqual(tx.state, 'draft')  # the customer may still be on eSewa
        self._age(tx, hours=1)
        with patch(SEND, return_value=payload):
            tx._esewa_sync_status()
        self.assertEqual(tx.state, 'cancel')

    def test_completed_payment_recovers_canceled_transaction(self):
        tx = self._create_transaction('redirect', state='cancel')
        uuid = tx._esewa_get_transaction_uuid()
        self._age(tx, hours=1)
        with patch(SEND, return_value={'transaction_uuid': uuid, 'total_amount': 10.0, 'status': 'COMPLETE'}):
            self.env['payment.transaction']._esewa_cron_check_pending()
        self.assertEqual(tx.state, 'cancel')  # not for another amount
        with patch(SEND, return_value={'transaction_uuid': uuid, 'total_amount': 1000.0, 'status': 'COMPLETE',
                                       'ref_id': 'LATE1'}):
            self.env['payment.transaction']._esewa_cron_check_pending()
        self.assertEqual(tx.state, 'done')
        self.assertEqual(tx.provider_reference, 'LATE1')

    def test_transaction_uuid_is_random_and_unique(self):
        first = self._create_transaction('redirect', reference='EMI/2026/00014')
        second = self._create_transaction('redirect', reference='EMI-2026-00014')
        uuids = {first._esewa_get_transaction_uuid(), second._esewa_get_transaction_uuid()}
        self.assertEqual(len(uuids), 2)
        self.assertNotIn('EMI-2026-00014', uuids)
        with self.assertRaises(IntegrityError), mute_logger('odoo.sql_db'):
            second.esewa_transaction_uuid = first.esewa_transaction_uuid
            second.flush_recordset()
        found = self.env['payment.transaction']._search_by_reference('esewa', {'transaction_uuid': first.esewa_transaction_uuid})
        self.assertEqual(found, first)

    def test_disabled_provider_is_never_used(self):
        tx = self._create_transaction('redirect')
        tx._esewa_get_transaction_uuid()
        self.esewa.state = 'disabled'
        with self.assertRaises(ValidationError):
            tx._get_specific_rendering_values(None)
        with self.assertRaises(ValidationError):
            self.esewa._build_request_url('')
        with patch(SEND) as send:
            tx._esewa_sync_status()
        send.assert_not_called()
        self.assertEqual(tx.state, 'draft')

    def test_only_test_mode_uses_the_sandbox(self):
        self.assertEqual(self.esewa._esewa_get_form_url(), const.FORM_URLS['test'])
        self.assertEqual(self.esewa._build_request_url(''), const.STATUS_URLS['test'])
        self.esewa.state = 'enabled'
        self.assertEqual(self.esewa._esewa_get_form_url(), const.FORM_URLS['enabled'])
        self.assertEqual(self.esewa._build_request_url(''), const.STATUS_URLS['enabled'])

    def test_credentials_are_not_copied(self):
        company = self.env['res.company'].create({'name': 'Another Finance Co'})
        provider = self.env['payment.provider'].search([('code', '=', 'esewa'), ('company_id', '=', company.id)])
        self.assertTrue(provider)
        self.assertFalse(provider.esewa_product_code)
        self.assertFalse(provider.esewa_secret_key)

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

    def _failure_redirect(self, tx, status, monitored=True):
        uuid = tx._esewa_get_transaction_uuid()
        self.authenticate(None, None, session_extra={
            PaymentPostProcessing.MONITORED_TX_ID_KEY: tx.id if monitored else False,
        })
        with patch(SEND, return_value={'transaction_uuid': uuid, 'total_amount': 1000.0, 'status': status}) as send:
            self._make_http_get_request(self._build_url(EsewaController._failure_url), params={'uuid': uuid})
        return send

    def test_failure_route_cancels(self):
        tx = self._create_transaction('redirect')
        self._failure_redirect(tx, 'CANCELED')
        self.assertEqual(tx.state, 'cancel')

    def test_failure_route_trusts_the_status_api(self):
        pending = self._create_transaction('redirect', reference='tx-pending')
        self._failure_redirect(pending, 'PENDING')
        self.assertEqual(pending.state, 'pending')
        young = self._create_transaction('redirect', reference='tx-young')
        self._failure_redirect(young, 'NOT_FOUND')
        self.assertEqual(young.state, 'draft')

    def test_failure_route_ignores_other_sessions(self):
        tx = self._create_transaction('redirect')
        send = self._failure_redirect(tx, 'CANCELED', monitored=False)
        send.assert_not_called()
        self.assertEqual(tx.state, 'draft')
