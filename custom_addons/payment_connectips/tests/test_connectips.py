# Part of Odoo. See LICENSE file for full copyright and licensing details.

import base64
import datetime
from unittest.mock import patch

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID

from odoo.exceptions import ValidationError
from odoo.tests import tagged

from odoo.addons.payment.tests.common import PaymentCommon
from odoo.addons.payment.tests.http_common import PaymentHttpCommon
from odoo.addons.payment_connectips import const
from odoo.addons.payment_connectips.controllers.main import ConnectipsController

SEND = 'odoo.addons.payment.models.payment_provider.PaymentProvider._send_api_request'


def _make_pfx(password):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'CREDITOR')])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(1).not_valid_before(now).not_valid_after(now + datetime.timedelta(days=1))
            .sign(key, hashes.SHA256()))
    pfx = pkcs12.serialize_key_and_certificates(
        b'creditor', key, cert, None, serialization.BestAvailableEncryption(password.encode()),
    )
    return key.public_key(), base64.b64encode(pfx)


class ConnectipsCommon(PaymentCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.public_key, pfx = _make_pfx('pfx-pass')
        cls.connectips = cls._prepare_provider('connectips', update_values={
            'connectips_merchant_id': '550',
            'connectips_app_id': 'MER-550-APP-1',
            'connectips_app_name': 'EMI Platform',
            'connectips_password': 'api-pass',
            'connectips_certificate': pfx,
            'connectips_certificate_password': 'pfx-pass',
        })
        cls.provider = cls.connectips
        cls.currency = cls._enable_currency('NPR')
        cls.amount = 500.0

    def _verify(self, token, message):
        self.public_key.verify(base64.b64decode(token), message.encode(), padding.PKCS1v15(), hashes.SHA256())


@tagged('post_install', '-at_install')
class TestConnectips(ConnectipsCommon):

    def test_login_form_is_signed(self):
        tx = self._create_transaction('redirect', reference='EMI/2026/00001-1')
        rendering = tx._get_specific_rendering_values(None)
        values = rendering['connectips_values']
        self.assertEqual(rendering['api_url'], 'https://uat.connectips.com/connectipswebgw/loginpage')
        self.assertEqual(values['TXNAMT'], '50000')  # paisa
        self.assertRegex(values['TXNDATE'], r'^\d{2}-\d{2}-\d{4}$')
        self.assertLessEqual(len(values['TXNID']), 20)
        self.assertEqual(values['REFERENCEID'], 'EMI/2026/00001-1')
        message = ','.join(f'{k}={values[k]}' for k in const.LOGIN_TOKEN_FIELDS) + ',TOKEN=TOKEN'
        self._verify(values['TOKEN'], message)  # raises if the signature is wrong

    def test_certificate_is_required(self):
        with self.assertRaises(ValidationError):
            self.connectips.connectips_certificate = False

    def test_signing_error_reaches_the_payment_form(self):
        """ The redirect form still renders, so the error state and message reach the customer. """
        self.connectips.connectips_certificate_password = 'wrong'
        tx = self._create_transaction('redirect')
        processing_values = tx._get_processing_values()
        self.assertEqual(processing_values['state'], 'error')
        self.assertIn("certificate", processing_values['state_message'])
        self.assertEqual(tx._get_specific_rendering_values(None), {'api_url': '', 'connectips_values': {}})

    def test_validation_request_and_success(self):
        tx = self._create_transaction('redirect')
        tx._get_specific_rendering_values(None)
        response = {'merchantId': 550, 'appId': 'MER-550-APP-1', 'referenceId': tx.connectips_txn_id,
                    'txnAmt': '50000', 'token': 'x', 'status': 'SUCCESS', 'statusDesc': 'TRANSACTION SUCCESSFULL'}
        with patch(SEND, return_value=response) as send:
            tx._connectips_sync_status()
        payload = send.call_args.kwargs['json']
        self.assertEqual(send.call_args.args[:2], ('POST', const.VALIDATE_ENDPOINT))
        self.assertEqual(payload['merchantId'], 550)
        self.assertEqual(payload['referenceId'], tx.connectips_txn_id)
        self.assertEqual(payload['txnAmt'], '50000')
        self._verify(payload['token'],
                     f'MERCHANTID=550,APPID=MER-550-APP-1,REFERENCEID={tx.connectips_txn_id},TXNAMT=50000')
        self.assertEqual(tx.state, 'done')

    def test_basic_auth(self):
        self.assertEqual(self.connectips._build_request_auth(), ('MER-550-APP-1', 'api-pass'))

    def test_disabled_provider_does_not_use_uat(self):
        self.connectips.state = 'enabled'
        self.assertEqual(self.connectips._build_request_url(const.VALIDATE_ENDPOINT),
                         const.DEFAULT_BASE_URLS['enabled'] + const.VALIDATE_ENDPOINT)
        self.connectips.state = 'disabled'
        with self.assertRaises(ValidationError):
            self.connectips._build_request_url(const.VALIDATE_ENDPOINT)

    def test_failed_and_error_statuses(self):
        tx = self._create_transaction('redirect', reference='tx-failed')
        tx._get_specific_rendering_values(None)
        with patch(SEND, return_value={'status': 'FAILED', 'statusDesc': 'TRANSACTION FAILED', 'txnAmt': '50000'}):
            tx._connectips_sync_status()
        self.assertEqual(tx.state, 'cancel')
        tx = self._create_transaction('redirect', reference='tx-error')
        tx._get_specific_rendering_values(None)
        with patch(SEND, return_value={'status': 'ERROR', 'statusDesc': 'retry', 'txnAmt': '50000'}):
            tx._connectips_sync_status()
        self.assertEqual(tx.state, 'pending')

    def test_amount_mismatch_rejected(self):
        tx = self._create_transaction('redirect')
        tx._get_specific_rendering_values(None)
        with patch(SEND, return_value={'status': 'SUCCESS', 'txnAmt': '100'}):
            tx._connectips_sync_status()
        self.assertEqual(tx.state, 'error')

    def test_redirect_urls_to_register(self):
        self.assertTrue(self.connectips.connectips_success_url.endswith(ConnectipsController._return_url))
        self.assertTrue(self.connectips.connectips_failure_url.endswith(ConnectipsController._failure_url))


@tagged('post_install', '-at_install')
class TestConnectipsHttp(ConnectipsCommon, PaymentHttpCommon):

    def test_return_route_validates(self):
        tx = self._create_transaction('redirect')
        tx._get_specific_rendering_values(None)
        with patch(SEND, return_value={'status': 'SUCCESS', 'txnAmt': '50000', 'referenceId': tx.connectips_txn_id}):
            self._make_http_get_request(self._build_url(ConnectipsController._return_url),
                                        params={'TXNID': tx.connectips_txn_id})
        self.assertEqual(tx.state, 'done')

    def test_failure_route_cancels(self):
        tx = self._create_transaction('redirect')
        tx._get_specific_rendering_values(None)
        with patch(SEND, return_value={'status': 'ERROR', 'txnAmt': '50000'}):
            self._make_http_get_request(self._build_url(ConnectipsController._failure_url),
                                        params={'TXNID': tx.connectips_txn_id})
        self.assertEqual(tx.state, 'cancel')
