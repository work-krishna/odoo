# Part of Odoo. See LICENSE file for full copyright and licensing details.

import base64
import hashlib
import hmac
import io
import uuid
from datetime import timedelta

import qrcode

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from odoo.addons.payment.logging import get_payment_logger
from odoo.addons.payment_fonepay import const
from odoo.addons.payment_fonepay.controllers.main import FonepayController


_logger = get_payment_logger(__name__)


class PaymentTransaction(models.Model):
    _inherit = 'payment.transaction'

    fonepay_qr_message = fields.Char(
        string="Fonepay QR Data",
        help="The raw string returned by Fonepay that is encoded into the QR code image shown "
             "to the customer.",
        readonly=True,
    )
    fonepay_prn = fields.Char(
        string="Fonepay PRN",
        help="The Product Number sent to Fonepay to identify this payment request. A fresh one "
             "is generated for every QR request and reused for the status checks that follow it.",
        readonly=True,
        copy=False,
    )

    # === BUSINESS METHODS === #

    def _get_specific_rendering_values(self, processing_values):
        """ Override of `payment` to request a Fonepay dynamic QR code and return the values
        needed to render the redirect form.

        Note: self.ensure_one() from `_get_processing_values`

        :param dict processing_values: The generic and specific processing values of the
                                        transaction.
        :return: The dict of provider-specific rendering values.
        :rtype: dict
        """
        if self.provider_code != 'fonepay':
            return super()._get_specific_rendering_values(processing_values)

        try:
            self._fonepay_request_qr()
        except ValidationError as error:
            self._set_error(str(error))
            return {}

        return {
            'api_url': FonepayController._process_url,
            'reference': self.reference,
        }

    def _fonepay_request_qr(self):
        """ Request a dynamic QR code from Fonepay for the transaction amount.

        Note: self.ensure_one()

        :return: None
        :raise ValidationError: If Fonepay rejects the request or returns no QR data.
        """
        self.ensure_one()
        provider_sudo = self.provider_id.sudo()
        prn = self._fonepay_get_prn()
        amount = self._fonepay_format_amount(self.amount)
        remarks1 = (self.reference or '')[:25]
        remarks2 = (self.company_id.name or 'Odoo')[:25]
        message = ','.join((amount, prn, provider_sudo.fonepay_merchant_code, remarks1, remarks2))
        payload = {
            'amount': amount,
            'remarks1': remarks1,
            'remarks2': remarks2,
            'prn': prn,
            'merchantCode': provider_sudo.fonepay_merchant_code,
            'dataValidation': self._fonepay_sign(provider_sudo.fonepay_secret_key, message),
            'username': provider_sudo.fonepay_username,
            'password': provider_sudo.fonepay_password,
        }
        response_data = provider_sudo._send_api_request(
            'POST', const.QR_REQUEST_ENDPOINT, json=payload, reference=self.reference,
        )
        if not response_data.get('success') or not response_data.get('qrMessage'):
            raise ValidationError(
                response_data.get('message') or _("Fonepay did not return a QR code.")
            )
        self.fonepay_qr_message = response_data['qrMessage']

    def _fonepay_check_qr_status(self):
        """ Ask Fonepay for the status of the QR payment and update the transaction accordingly.

        Odoo has no direct webhook from Fonepay: payment notifications are pushed over a
        WebSocket connection instead. Rather than keeping a persistent WebSocket connection open
        in an Odoo worker, the customer's browser polls this method (through the `/payment/fonepay/poll`
        route) while the QR code is displayed, and it falls back to Fonepay's "Check QR Request
        Status" API. Errors are swallowed so that a transient network hiccup does not interrupt
        the polling; the check simply happens again on the next poll.

        Note: self.ensure_one()

        :return: None
        """
        self.ensure_one()
        if self.provider_code != 'fonepay' or self.state != 'pending':
            return

        if self._fonepay_has_timed_out():
            self._set_canceled(state_message=_(
                "The Fonepay QR code expired before the payment was completed. Please try again."
            ))
            return

        provider_sudo = self.provider_id.sudo()
        prn = self._fonepay_get_prn()
        message = ','.join((prn, provider_sudo.fonepay_merchant_code))
        payload = {
            'prn': prn,
            'merchantCode': provider_sudo.fonepay_merchant_code,
            'dataValidation': self._fonepay_sign(provider_sudo.fonepay_secret_key, message),
            'username': provider_sudo.fonepay_username,
            'password': provider_sudo.fonepay_password,
        }
        try:
            status_data = provider_sudo._send_api_request(
                'POST', const.QR_STATUS_ENDPOINT, json=payload, reference=self.reference,
            )
        except ValidationError:
            _logger.warning(
                "Could not fetch the Fonepay QR status for transaction %s.", self.reference
            )
            return
        self._process('fonepay', status_data)

    def _fonepay_has_timed_out(self):
        """ Return whether this pending transaction has been waiting for payment for longer than
        the provider's configured timeout.

        The clock starts at `last_state_change`, which is set the moment the transaction becomes
        'pending' (i.e. as soon as the customer is shown the QR code).

        Note: self.ensure_one()

        :return: Whether the transaction has timed out.
        :rtype: bool
        """
        self.ensure_one()
        timeout = self.provider_id.sudo().fonepay_payment_timeout
        if not timeout or not self.last_state_change:
            return False
        deadline = self.last_state_change + timedelta(seconds=timeout)
        return fields.Datetime.now() > deadline

    @api.model
    def _fonepay_cron_expire_pending(self):
        """ Cancel pending Fonepay transactions that have timed out.

        This is a backstop for customers who never come back to the payment status page (e.g. they
        closed the tab): `_fonepay_check_qr_status` already handles the timeout for the customer
        actively watching the QR code, but nothing would otherwise expire an abandoned one.

        :return: None
        """
        pending_txs = self.search([('provider_code', '=', 'fonepay'), ('state', '=', 'pending')])
        for tx in pending_txs:
            if tx._fonepay_has_timed_out():
                tx._set_canceled(state_message=_(
                    "The Fonepay QR code expired before the payment was completed."
                ))

    def _fonepay_get_qr_code(self):
        """ Return the QR code image of the transaction, as a base64-encoded data URL.

        Note: self.ensure_one()

        :return: The base64 QR code image, or None if no QR data is available yet.
        :rtype: str|None
        """
        self.ensure_one()
        if not self.fonepay_qr_message:
            return None
        qr = qrcode.QRCode(border=2, box_size=6)
        qr.add_data(self.fonepay_qr_message)
        qr.make(fit=True)
        image = qr.make_image()
        buffer = io.BytesIO()
        image.save(buffer, format='PNG')
        return 'data:image/png;base64,' + base64.b64encode(buffer.getvalue()).decode()

    def _fonepay_get_prn(self):
        """ Return the Product Number (prn) used to identify the transaction on Fonepay's side.

        A new prn is generated the first time this is called for a transaction (i.e. when the QR
        code is requested) and then persisted, so that the status checks that follow reuse the
        exact same value Fonepay was given when the QR code was created.

        Note: self.ensure_one()

        :return: The prn.
        :rtype: str
        """
        self.ensure_one()
        if not self.fonepay_prn:
            self.fonepay_prn = self._fonepay_generate_prn()
        return self.fonepay_prn

    @staticmethod
    def _fonepay_generate_prn():
        """ Generate a new, random hexadecimal Product Number (prn).

        Formatted the way Fonepay's own examples are (e.g. "5d76d323-d1f6"): two dash-separated
        hex groups, well within the 25 character limit, and different on every call so that two
        QR requests never collide on the same prn.

        :return: The generated prn.
        :rtype: str
        """
        token = uuid.uuid4().hex
        return f'{token[:8]}-{token[8:12]}'

    @staticmethod
    def _fonepay_format_amount(amount):
        """ Format an amount the way Fonepay expects it: digits only, with a single '.' as the
        decimal separator, and no separator at all for whole numbers.

        :param float amount: The amount to format.
        :return: The formatted amount.
        :rtype: str
        """
        amount = float(amount)
        if amount == int(amount):
            return str(int(amount))
        return f'{amount:.2f}'

    @staticmethod
    def _fonepay_sign(secret_key, message):
        """ Compute the Data Validation Token (HMAC_SHA512) expected by Fonepay.

        :param str secret_key: The merchant's Fonepay secret key.
        :param str message: The comma-separated message to sign.
        :return: The hex-encoded signature.
        :rtype: str
        """
        return hmac.new(secret_key.encode(), message.encode(), hashlib.sha512).hexdigest()

    # === OVERRIDES === #

    def _extract_amount_data(self, payment_data):
        """ Override of `payment` to skip the amount validation.

        Fonepay's QR status check does not return the amount; it was already sent to, and
        acknowledged by, Fonepay when the QR code was requested.
        """
        if self.provider_code != 'fonepay':
            return super()._extract_amount_data(payment_data)
        return None

    def _apply_updates(self, payment_data):
        """ Override of `payment` to update the transaction based on the payment data. """
        if self.provider_code != 'fonepay':
            return super()._apply_updates(payment_data)

        if 'paymentStatus' not in payment_data:
            # The transaction is only just being redirected back after the QR code was created.
            self._set_pending()
            return

        if payment_data.get('fonepayTraceId'):
            self.provider_reference = str(payment_data['fonepayTraceId'])

        payment_status = payment_data.get('paymentStatus')
        if payment_status == 'success':
            self._set_done()
        # Note: Fonepay's own documentation shows the exact same payload for the "pending" and
        # "failed" statuses, so a non-'success' status returned by the status check is not
        # treated as a definitive failure here. The transaction is left pending and re-checked on
        # the next poll; it can still be canceled manually from the backend if needed.
