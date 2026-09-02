# Part of Odoo. See LICENSE file for full copyright and licensing details.

from unittest.mock import patch

from odoo.exceptions import ValidationError
from odoo.tests import tagged

from odoo.addons.payment_fonepay.tests.common import FonepayCommon


@tagged('post_install', '-at_install')
class TestPaymentTransaction(FonepayCommon):

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

    def test_prn_is_the_transaction_id(self):
        """ Test that the prn sent to Fonepay is short, stable, and unique. """
        tx = self._create_transaction('redirect')
        self.assertEqual(tx._fonepay_get_prn(), str(tx.id))

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
