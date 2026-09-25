# Part of Odoo. See LICENSE file for full copyright and licensing details.

import base64
import hashlib
import hmac
from datetime import timedelta
from uuid import uuid4

from werkzeug.urls import url_encode

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from odoo.addons.payment.logging import get_payment_logger
from odoo.addons.payment_esewa import const
from odoo.addons.payment_esewa.controllers.main import EsewaController


_logger = get_payment_logger(__name__)


class PaymentTransaction(models.Model):
    _inherit = 'payment.transaction'

    esewa_transaction_uuid = fields.Char(
        string="eSewa Transaction UUID",
        help="The transaction_uuid sent to eSewa: random, unique, letters, digits and hyphens only.",
        readonly=True, copy=False,
    )

    _esewa_transaction_uuid_unique = models.UniqueIndex(
        '(esewa_transaction_uuid) WHERE esewa_transaction_uuid IS NOT NULL',
        "An eSewa transaction UUID can only be used once.",
    )

    # === BUSINESS METHODS - PAYMENT FLOW === #

    def _get_specific_rendering_values(self, processing_values):
        """ Override of `payment` to return the signed eSewa ePay v2 form values.

        Note: self.ensure_one() from `_get_processing_values`
        """
        if self.provider_code != 'esewa':
            return super()._get_specific_rendering_values(processing_values)

        provider_sudo = self.provider_id.sudo()
        form_url = provider_sudo._esewa_get_form_url()  # Refuses disabled providers.
        uuid = self._esewa_get_transaction_uuid()
        total = self._esewa_format_amount(self.amount)
        base_url = provider_sudo.get_base_url()
        values = {
            'amount': total,
            'tax_amount': '0',
            'total_amount': total,
            'transaction_uuid': uuid,
            'product_code': provider_sudo.esewa_product_code,
            'product_service_charge': '0',
            'product_delivery_charge': '0',
            'success_url': f'{base_url}{EsewaController._return_url}',
            'failure_url': f'{base_url}{EsewaController._failure_url}?{url_encode({"uuid": uuid})}',
            'signed_field_names': ','.join(const.REQUEST_SIGNED_FIELDS),
        }
        values['signature'] = self._esewa_sign(
            provider_sudo.esewa_secret_key, const.REQUEST_SIGNED_FIELDS, values,
        )
        return {'api_url': form_url, 'esewa_values': values}

    def _esewa_get_transaction_uuid(self):
        """ The uuid is the only thing tying eSewa's status to this transaction: keep it
        unguessable (the failure URL is public) and independent of the reference. """
        self.ensure_one()
        if not self.esewa_transaction_uuid:
            self.esewa_transaction_uuid = f'{self.id}-{uuid4().hex[:12]}'
        return self.esewa_transaction_uuid

    @staticmethod
    def _esewa_format_amount(amount):
        """ eSewa signs the literal string it receives: keep one canonical format. """
        amount = round(float(amount), 2)
        return str(int(amount)) if amount == int(amount) else f'{amount:.2f}'

    @staticmethod
    def _esewa_sign(secret_key, field_names, data):
        """ Base64 HMAC-SHA256 of 'k1=v1,k2=v2,...' over ``field_names`` in order. """
        message = ','.join(f'{name}={data.get(name, "")}' for name in field_names)
        digest = hmac.new(secret_key.encode(), message.encode(), hashlib.sha256).digest()
        return base64.b64encode(digest).decode()

    def _esewa_verify_signature(self, data):
        """ Check the signature of the data eSewa redirected back with. """
        self.ensure_one()
        field_names = (data.get('signed_field_names') or '').split(',')
        secret_key = self.provider_id.sudo().esewa_secret_key
        if not secret_key or not data.get('signature') or not field_names or field_names == ['']:
            return False
        expected = self._esewa_sign(secret_key, field_names, data)
        return hmac.compare_digest(expected, data['signature'])

    def _esewa_fetch_status(self):
        """ Ask eSewa's status API for the authoritative state of the payment. """
        self.ensure_one()
        provider_sudo = self.provider_id.sudo()
        return provider_sudo._send_api_request('GET', '', params={
            'product_code': provider_sudo.esewa_product_code,
            'total_amount': self._esewa_format_amount(self.amount),
            'transaction_uuid': self._esewa_get_transaction_uuid(),
        }, reference=self.reference)

    def _esewa_sync_status(self):
        """ Refresh transactions from the status API (errors are logged, not raised).

        Canceled transactions are checked too: a payment completed on eSewa after Odoo
        gave up on it must still be recorded. """
        for tx in self.filtered(lambda t: t.provider_code == 'esewa' and t.esewa_transaction_uuid
                                and t.state in ('draft', 'pending', 'cancel')):
            if tx.provider_id.state == 'disabled':
                _logger.warning("eSewa provider %s is disabled: transaction %s not checked.",
                                tx.provider_id.id, tx.reference)
                continue
            try:
                status_data = tx._esewa_fetch_status()
            except ValidationError:
                _logger.warning("Could not fetch the eSewa status of transaction %s.", tx.reference)
                continue
            if tx.state == 'cancel' and status_data.get('status') not in const.STATUS_MAPPING['done']:
                continue  # Still not paid.
            tx._process('esewa', status_data)

    @api.model
    def _esewa_cron_check_pending(self):
        """ Settle eSewa payments whose customer never came back to Odoo, and recover
        recently canceled ones that eSewa completed after all. """
        now = fields.Datetime.now()
        self.search([
            ('provider_code', '=', 'esewa'), ('esewa_transaction_uuid', '!=', False),
            ('create_date', '<=', now - timedelta(minutes=5)),
            '|', ('state', 'in', ('draft', 'pending')),
            '&', ('state', '=', 'cancel'), ('create_date', '>=', now - const.RECOVERY_WINDOW),
        ], limit=100)._esewa_sync_status()

    # === OVERRIDES - NOTIFICATION PROCESSING === #

    @api.model
    def _search_by_reference(self, provider_code, payment_data):
        """ Override of `payment` to find the transaction from eSewa's transaction_uuid. """
        if provider_code != 'esewa':
            return super()._search_by_reference(provider_code, payment_data)
        uuid = payment_data.get('transaction_uuid')
        tx = uuid and self.search([('esewa_transaction_uuid', '=', uuid), ('provider_code', '=', 'esewa')], limit=2)
        if not tx:
            _logger.warning("No eSewa transaction found for transaction_uuid %s.", uuid)
            return self
        if len(tx) > 1:
            _logger.warning("Several eSewa transactions share transaction_uuid %s: ignored.", uuid)
            return self
        return tx

    def _extract_amount_data(self, payment_data):
        """ Override of `payment` to return the amount eSewa confirmed. """
        if self.provider_code != 'esewa':
            return super()._extract_amount_data(payment_data)
        return {
            'amount': float(str(payment_data.get('total_amount', 0)).replace(',', '')),
            'currency_code': 'NPR',
        }

    def _apply_updates(self, payment_data):
        """ Override of `payment` to update the transaction from eSewa's status. """
        if self.provider_code != 'esewa':
            return super()._apply_updates(payment_data)

        status = payment_data.get('status')
        if self.state == 'cancel':
            # Only a completed payment of the right amount brings a canceled transaction back
            # (the generic amount check cannot flag a canceled transaction as an error).
            amount = self._extract_amount_data(payment_data)['amount']
            if status not in const.STATUS_MAPPING['done'] or self.currency_id.compare_amounts(amount, self.amount):
                return
        reference = payment_data.get('transaction_code') or payment_data.get('ref_id')
        if reference:
            self.provider_reference = reference
        if status in const.STATUS_MAPPING['done']:
            self._set_done(extra_allowed_states=('cancel',))
        elif status in const.STATUS_MAPPING['pending']:
            self._set_pending()
        elif status in const.STATUS_MAPPING['cancel']:
            if status == 'NOT_FOUND' and self.create_date > fields.Datetime.now() - const.NOT_FOUND_GRACE:
                # eSewa also answers NOT_FOUND while the customer is still on its payment page.
                _logger.info("eSewa has no payment yet for transaction %s; checking again later.", self.reference)
                return
            self._set_canceled(state_message=_("The payment was not completed on eSewa."))
        elif status in const.STATUS_MAPPING['error']:
            self._set_error(_("eSewa reports the payment as refunded (%s).", status))
        else:
            _logger.warning("Unknown eSewa status %s for transaction %s.", status, self.reference)
            self._set_error(_("Received an unknown payment status from eSewa: %s", status))
