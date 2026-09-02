# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo.addons.payment.tests.common import PaymentCommon


class FonepayCommon(PaymentCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.fonepay = cls._prepare_provider('fonepay', update_values={
            'fonepay_merchant_code': 'fonepay123',
            'fonepay_username': 'bijayk',
            'fonepay_password': 'password',
            'fonepay_secret_key': 'fonepay',
        })
        cls.provider = cls.fonepay
        cls.currency = cls._enable_currency('NPR')
        cls.amount = 14.0

        # The example from Fonepay's technical specification document (section 3.1.2).
        cls.sample_qr_response = {
            'message': "successfull",
            'qrMessage': "00020101021215313791052400520446000000NBQM:29226400011fonepay",
            'status': "CREATED",
            'statusCode': 201,
            'success': True,
            'thirdpartyQrWebSocketUrl': "wss://dev-ws.fonepay.com/merchantEndPoint/xyz/NBQM/Y",
        }
        cls.sample_status_success = {
            'fonepayTraceId': 17404,
            'merchantCode': "NBQM",
            'paymentStatus': "success",
            'prn': "5d76d323-d1f6",
        }
        cls.sample_status_pending = {
            'fonepayTraceId': 17420,
            'merchantCode': "NBQM",
            'paymentStatus': "failed",  # As documented, Fonepay reuses this shape while pending.
            'prn': "654df0eb-0740",
        }
