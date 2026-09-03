# Part of Odoo. See LICENSE file for full copyright and licensing details.

from datetime import timedelta
from unittest.mock import patch

from odoo.exceptions import ValidationError
from odoo.tests import tagged

from odoo.addons.payment_fonepay.tests.common import FonepayCommon


@tagged('post_install', '-at_install')
class TestPaymentTransaction(FonepayCommon):

    def setUp(self):
        # `PaymentCommon` mocks `_post_process` (when `account_payment` is installed) to avoid
        # real accounting side effects in tests. We want the real thing here, since it's exactly
        # what `test_check_qr_status_post_processes_immediately_on_success` verifies.
        self.enable_post_process_patcher = False
        super().setUp()

    def test_signature_matches_fonepay_documentation_sample(self):
        """ Test the HMAC_SHA512 signature against the worked examples from Fonepay's technical
        specification document (section 3.1.2 and 3.3.2). """
        tx = self.env['payment.transaction']
        key = 'a7e3512f5032480a83137793cb2021dc'

        qr_request_signature = tx._fonepay_sign(key, '14,5d76d323-d1f6,NBQM,test1,test2')
        self.assertEqual(
            qr_request_signature,
            '5ae718032328ae5615fa4694dfbf3ecd13432bd49031e7285a3f8bc122ecbb8e833e83c7a11f89'
            '5d30f3e8fd1906317aece113675166ae0d804ecf32a8bbdbaf',
        )

        status_check_signature = tx._fonepay_sign(key, '5d76d323-d1f6-4a38,NBQM')
        self.assertEqual(
            status_check_signature,
            'b816affc4599162bdbd9b8c7f6b7b83508dadfcceb0d58ba01f1042d749a7b5d71ea5b6f409ca'
            '2d61607043555733c9240d2651a3473e7a195a326b21e9fafe8',
        )

    def test_format_amount(self):
        """ Test that amounts are formatted without a needless decimal part or trailing zeros. """
        tx = self.env['payment.transaction']
        self.assertEqual(tx._fonepay_format_amount(14), '14')
        self.assertEqual(tx._fonepay_format_amount(14.0), '14')
        self.assertEqual(tx._fonepay_format_amount(14.5), '14.50')

    def test_prn_format(self):
        """ Test that generated prns are hex, dash-separated, and well within the 25 character
        limit, matching the shape of Fonepay's own examples (e.g. "5d76d323-d1f6"). """
        prn = self.env['payment.transaction']._fonepay_generate_prn()
        self.assertRegex(prn, r'^[0-9a-f]{8}-[0-9a-f]{4}$')
        self.assertLessEqual(len(prn), 25)

    def test_prn_is_unique_per_transaction_and_stable_across_calls(self):
        """ Test that each transaction gets its own prn, generated once and then reused. """
        tx1 = self._create_transaction('redirect', reference='Test Transaction 1')
        tx2 = self._create_transaction('redirect', reference='Test Transaction 2')

        prn1 = tx1._fonepay_get_prn()
        prn2 = tx2._fonepay_get_prn()

        self.assertNotEqual(prn1, prn2)
        self.assertEqual(tx1._fonepay_get_prn(), prn1)  # Calling it again reuses the stored value.
        self.assertEqual(tx1.fonepay_prn, prn1)

    def test_rendering_values_stores_qr_message_and_no_redirection_happens(self):
        """ Test that requesting the QR code stores the raw QR data and returns our own
        processing controller as the redirect target. """
        tx = self._create_transaction('redirect')
        with patch(
            'odoo.addons.payment.models.payment_provider.PaymentProvider._send_api_request',
            return_value=self.sample_qr_response,
        ):
            rendering_values = tx._get_specific_rendering_values(None)

        self.assertEqual(tx.fonepay_qr_message, self.sample_qr_response['qrMessage'])
        self.assertEqual(rendering_values['api_url'], '/payment/fonepay/process')
        self.assertEqual(rendering_values['reference'], tx.reference)

    def test_rendering_values_sets_error_state_on_failure(self):
        """ Test that a rejected QR request puts the transaction in an error state instead of
        crashing the checkout flow. """
        tx = self._create_transaction('redirect')
        with patch(
            'odoo.addons.payment.models.payment_provider.PaymentProvider._send_api_request',
            side_effect=ValidationError("Data Validation Failed"),
        ):
            rendering_values = tx._get_specific_rendering_values(None)

        self.assertEqual(rendering_values, {})
        self.assertEqual(tx.state, 'error')

    def test_apply_updates_process_sets_pending(self):
        """ Test that landing back on our controller after the QR code was created moves the
        transaction to 'pending'. """
        tx = self._create_transaction('redirect')
        tx._process('fonepay', {'reference': tx.reference})
        self.assertEqual(tx.state, 'pending')

    def test_apply_updates_success_sets_done(self):
        """ Test that a successful status check moves the transaction to 'done'. """
        tx = self._create_transaction('redirect')
        tx._set_pending()
        tx._process('fonepay', self.sample_status_success)
        self.assertEqual(tx.state, 'done')
        self.assertEqual(tx.provider_reference, str(self.sample_status_success['fonepayTraceId']))

    def test_apply_updates_non_success_keeps_transaction_pending(self):
        """ Test that a non-'success' status (ambiguous between "pending" and "failed" per
        Fonepay's documentation) does not cancel the transaction outright. """
        tx = self._create_transaction('redirect')
        tx._set_pending()
        tx._process('fonepay', self.sample_status_pending)
        self.assertEqual(tx.state, 'pending')

    def test_check_qr_status_skipped_when_not_pending(self):
        """ Test that the status is only checked while the transaction is 'pending', to avoid
        needless calls to Fonepay once the transaction has reached a final state. """
        tx = self._create_transaction('redirect')  # State is 'draft'.
        with patch(
            'odoo.addons.payment.models.payment_provider.PaymentProvider._send_api_request',
        ) as mock:
            tx._fonepay_check_qr_status()
        self.assertEqual(mock.call_count, 0)

    def test_has_not_timed_out_right_after_becoming_pending(self):
        """ Test that a freshly pending transaction has not timed out yet. """
        tx = self._create_transaction('redirect')
        tx._set_pending()
        self.assertFalse(tx._fonepay_has_timed_out())

    def test_has_timed_out_past_the_configured_timeout(self):
        """ Test that a transaction pending for longer than the provider's timeout is flagged. """
        self.provider.fonepay_payment_timeout = 60
        tx = self._create_transaction('redirect')
        tx._set_pending()
        tx.last_state_change -= timedelta(seconds=61)
        self.assertTrue(tx._fonepay_has_timed_out())

    def test_check_qr_status_cancels_on_timeout_without_calling_fonepay(self):
        """ Test that a timed-out transaction is canceled locally, without bothering Fonepay, and
        that the customer-facing message explains why. """
        self.provider.fonepay_payment_timeout = 60
        tx = self._create_transaction('redirect')
        tx._set_pending()
        tx.last_state_change -= timedelta(seconds=61)

        with patch(
            'odoo.addons.payment.models.payment_provider.PaymentProvider._send_api_request',
        ) as mock:
            tx._fonepay_check_qr_status()

        self.assertEqual(mock.call_count, 0)
        self.assertEqual(tx.state, 'cancel')
        self.assertIn('expired', tx.state_message)

    def test_check_qr_status_post_processes_immediately_on_success(self):
        """ Test that a successful status check triggers post-processing right away, instead of
        waiting for a page polling `/payment/status` or the slow generic cron. This matters most
        for flows with no such page open at all, e.g. a Point of Sale online payment. """
        tx = self._create_transaction('redirect')
        tx._set_pending()

        with patch(
            'odoo.addons.payment.models.payment_provider.PaymentProvider._send_api_request',
            return_value=self.sample_status_success,
        ):
            tx._fonepay_check_qr_status()

        self.assertEqual(tx.state, 'done')
        self.assertTrue(tx.is_post_processed)

    def test_cron_expires_only_timed_out_transactions(self):
        """ Test that the expiry cron cancels timed-out transactions and leaves fresh ones alone.
        """
        self.provider.fonepay_payment_timeout = 60

        expired_tx = self._create_transaction('redirect', reference='Expired Transaction')
        expired_tx._set_pending()
        expired_tx.last_state_change -= timedelta(seconds=61)

        fresh_tx = self._create_transaction('redirect', reference='Fresh Transaction')
        fresh_tx._set_pending()

        self.env['payment.transaction']._fonepay_cron_expire_pending()

        self.assertEqual(expired_tx.state, 'cancel')
        self.assertEqual(fresh_tx.state, 'pending')
