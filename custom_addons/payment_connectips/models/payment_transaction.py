# Part of Odoo. See LICENSE file for full copyright and licensing details.

import uuid
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from odoo.addons.payment.logging import get_payment_logger
from odoo.addons.payment_connectips import const


_logger = get_payment_logger(__name__)


class PaymentTransaction(models.Model):
    _inherit = 'payment.transaction'

    connectips_txn_id = fields.Char(
        string="connectIPS TXNID", readonly=True, copy=False, index='btree_not_null',
        help="The unique transaction id (max. 20 characters) sent to connectIPS.",
    )

    # === BUSINESS METHODS - PAYMENT FLOW === #

    def _get_specific_rendering_values(self, processing_values):
        """ Override of `payment` to return the signed connectIPS login page form.

        Note: self.ensure_one() from `_get_processing_values`
        """
        if self.provider_code != 'connectips':
            return super()._get_specific_rendering_values(processing_values)

        provider_sudo = self.provider_id.sudo()
        values = {
            'MERCHANTID': provider_sudo.connectips_merchant_id,
            'APPID': provider_sudo.connectips_app_id,
            'APPNAME': provider_sudo.connectips_app_name,
            'TXNID': self._connectips_get_txn_id(),
            'TXNDATE': fields.Date.context_today(self).strftime('%d-%m-%Y'),
            'TXNCRNCY': 'NPR',
            'TXNAMT': str(self._connectips_to_paisa(self.amount)),
            'REFERENCEID': self.reference[:20],
            'REMARKS': self.reference[:50],
            'PARTICULARS': (self.company_id.name or self.reference)[:100],
        }
        message = ','.join(f'{key}={values[key]}' for key in const.LOGIN_TOKEN_FIELDS) + ',TOKEN=TOKEN'
        try:
            values['TOKEN'] = provider_sudo._connectips_sign(message)
        except ValidationError as error:
            self._set_error(str(error))
            return {}
        return {
            'api_url': provider_sudo._build_request_url(const.LOGIN_PAGE_ENDPOINT),
            'connectips_values': values,
        }

    def _connectips_get_txn_id(self):
        self.ensure_one()
        if not self.connectips_txn_id:
            self.connectips_txn_id = f'{self.id}-{uuid.uuid4().hex[:8]}'[:20]
        return self.connectips_txn_id

    @staticmethod
    def _connectips_to_paisa(amount):
        return int(round(float(amount) * 100))

    def _connectips_validate(self):
        """ Ask connectIPS for the status of the payment. """
        self.ensure_one()
        provider_sudo = self.provider_id.sudo()
        txn_amt = str(self._connectips_to_paisa(self.amount))
        txn_id = self._connectips_get_txn_id()
        message = (f'MERCHANTID={provider_sudo.connectips_merchant_id},APPID={provider_sudo.connectips_app_id},'
                   f'REFERENCEID={txn_id},TXNAMT={txn_amt}')
        payload = {
            'merchantId': int(provider_sudo.connectips_merchant_id),
            'appId': provider_sudo.connectips_app_id,
            'referenceId': txn_id,
            'txnAmt': txn_amt,
            'token': provider_sudo._connectips_sign(message),
        }
        return provider_sudo._send_api_request(
            'POST', const.VALIDATE_ENDPOINT, json=payload, reference=self.reference,
        )

    def _connectips_sync_status(self):
        for tx in self.filtered(lambda t: t.provider_code == 'connectips' and t.connectips_txn_id
                                and t.state in ('draft', 'pending')):
            try:
                data = tx._connectips_validate()
            except ValidationError:
                _logger.warning("Could not validate connectIPS transaction %s.", tx.reference)
                continue
            tx._process('connectips', dict(data, referenceId=tx.connectips_txn_id))

    @api.model
    def _connectips_cron_check_pending(self):
        cutoff = fields.Datetime.now() - timedelta(minutes=5)
        self.search([
            ('provider_code', '=', 'connectips'), ('state', 'in', ('draft', 'pending')),
            ('connectips_txn_id', '!=', False), ('create_date', '<=', cutoff),
        ], limit=100)._connectips_sync_status()

    # === OVERRIDES - NOTIFICATION PROCESSING === #

    @api.model
    def _search_by_reference(self, provider_code, payment_data):
        """ Override of `payment` to find the transaction from connectIPS's TXNID. """
        if provider_code != 'connectips':
            return super()._search_by_reference(provider_code, payment_data)
        txn_id = payment_data.get('referenceId') or payment_data.get('TXNID')
        tx = txn_id and self.search([('connectips_txn_id', '=', txn_id), ('provider_code', '=', 'connectips')])
        if not tx:
            _logger.warning("No connectIPS transaction found for TXNID %s.", txn_id)
        return tx or self

    def _extract_amount_data(self, payment_data):
        """ Override of `payment` to validate the amount confirmed in paisa. """
        if self.provider_code != 'connectips':
            return super()._extract_amount_data(payment_data)
        if payment_data.get('status') != 'SUCCESS':
            return None
        return {'amount': int(float(payment_data.get('txnAmt') or 0)) / 100, 'currency_code': 'NPR'}

    def _apply_updates(self, payment_data):
        """ Override of `payment` to update the transaction from the validation status. """
        if self.provider_code != 'connectips':
            return super()._apply_updates(payment_data)
        status = payment_data.get('status')
        if status == 'SUCCESS':
            self.provider_reference = payment_data.get('referenceId') or self.connectips_txn_id
            self._set_done()
        elif status == 'FAILED':
            self._set_canceled(state_message=payment_data.get('statusDesc') or _("The connectIPS payment failed."))
        elif status == 'ERROR':
            # Validation errors are often transient (e.g. not yet settled): retry later.
            _logger.warning("connectIPS validation error for %s: %s", self.reference, payment_data.get('statusDesc'))
            self._set_pending()
        else:
            self._set_error(_("Received an unknown payment status from connectIPS: %s", status))
