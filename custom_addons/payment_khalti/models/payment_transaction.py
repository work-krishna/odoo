# Part of Odoo. See LICENSE file for full copyright and licensing details.

from datetime import timedelta
from urllib.parse import parse_qs, urlsplit, urlunsplit

import requests

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from odoo.addons.payment.logging import get_payment_logger
from odoo.addons.payment_khalti import const
from odoo.addons.payment_khalti.controllers.main import KhaltiController


_logger = get_payment_logger(__name__)


class PaymentTransaction(models.Model):
    _inherit = 'payment.transaction'

    khalti_pidx = fields.Char(
        string="Khalti pidx", readonly=True, copy=False, index='btree_not_null',
        help="The payment identifier returned by Khalti when the payment was initiated.",
    )

    # === BUSINESS METHODS - PAYMENT FLOW === #

    def _get_specific_rendering_values(self, processing_values):
        """ Override of `payment` to initiate the payment with Khalti and redirect to it.

        Note: self.ensure_one() from `_get_processing_values`
        """
        if self.provider_code != 'khalti':
            return super()._get_specific_rendering_values(processing_values)

        provider_sudo = self.provider_id.sudo()
        base_url = provider_sudo.get_base_url()
        partner = self.partner_id
        payload = {
            'return_url': f'{base_url}{KhaltiController._return_url}',
            'website_url': base_url,
            'amount': self._khalti_to_paisa(self.amount),
            'purchase_order_id': self.reference,
            'purchase_order_name': (self.company_id.name or self.reference)[:100],
            'customer_info': {
                key: value for key, value in (
                    ('name', self.partner_name or partner.name),
                    ('email', self.partner_email or partner.email),
                    ('phone', self.partner_phone or partner.phone),
                ) if value
            },
        }
        try:
            response = provider_sudo._send_api_request(
                'POST', const.INITIATE_ENDPOINT, json=payload, reference=self.reference,
            )
        except ValidationError as error:
            # Keep the error state (the payment form shows its message): render an empty form.
            self._set_error(str(error))
            return {'api_url': '', 'khalti_params': {}}
        self.khalti_pidx = response.get('pidx')
        # A GET form drops the action's query string, so pass pidx as a field.
        url = urlsplit(response.get('payment_url', ''))
        return {
            'api_url': urlunsplit((url.scheme, url.netloc, url.path, '', '')),
            'khalti_params': {key: values[0] for key, values in parse_qs(url.query).items()},
        }

    @staticmethod
    def _khalti_to_paisa(amount):
        return int(round(float(amount) * 100))

    def _khalti_lookup(self):
        """ Return Khalti's lookup data. Expired and canceled payments are
        reported with HTTP 400 and a JSON body, so both are read here. """
        self.ensure_one()
        provider_sudo = self.provider_id.sudo()
        url = provider_sudo._build_request_url(const.LOOKUP_ENDPOINT)
        payload = {'pidx': self.khalti_pidx}
        provider_sudo._log_request('POST', url, payload, reference=self.reference)
        try:
            response = requests.post(
                url, json=payload, timeout=10,
                headers=provider_sudo._build_request_headers('POST', const.LOOKUP_ENDPOINT, payload),
            )
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
            raise ValidationError(_("Could not establish the connection to Khalti."))
        provider_sudo._log_response(response, reference=self.reference)
        try:
            data = response.json()
        except ValueError:
            data = None
        if response.status_code not in (200, 400) or not isinstance(data, dict) or 'status' not in data:
            raise ValidationError(_("Unexpected Khalti lookup response: %s", response.text[:200]))
        return data

    def _khalti_sync_status(self):
        for tx in self.filtered(lambda t: t.provider_code == 'khalti' and t.khalti_pidx
                                and t.state in ('draft', 'pending')):
            try:
                data = tx._khalti_lookup()
            except ValidationError:
                _logger.warning("Could not look up Khalti transaction %s.", tx.reference)
                continue
            tx._process('khalti', dict(data, pidx=tx.khalti_pidx))

    @api.model
    def _khalti_cron_check_pending(self):
        cutoff = fields.Datetime.now() - timedelta(minutes=5)
        self.search([
            ('provider_code', '=', 'khalti'), ('state', 'in', ('draft', 'pending')),
            ('khalti_pidx', '!=', False), ('create_date', '<=', cutoff),
        ], limit=100)._khalti_sync_status()

    # === OVERRIDES - NOTIFICATION PROCESSING === #

    @api.model
    def _search_by_reference(self, provider_code, payment_data):
        """ Override of `payment` to find the transaction from Khalti's pidx. """
        if provider_code != 'khalti':
            return super()._search_by_reference(provider_code, payment_data)
        pidx = payment_data.get('pidx')
        tx = pidx and self.search([('khalti_pidx', '=', pidx), ('provider_code', '=', 'khalti')])
        if not tx:
            _logger.warning("No Khalti transaction found for pidx %s.", pidx)
        return tx or self

    def _extract_amount_data(self, payment_data):
        """ Override of `payment` to validate the amount Khalti confirmed (in paisa). """
        if self.provider_code != 'khalti':
            return super()._extract_amount_data(payment_data)
        if payment_data.get('status') not in const.STATUS_MAPPING['done']:
            return None  # Canceled/expired lookups carry no amount.
        return {'amount': int(payment_data.get('total_amount') or 0) / 100, 'currency_code': 'NPR'}

    def _apply_updates(self, payment_data):
        """ Override of `payment` to update the transaction from Khalti's lookup status. """
        if self.provider_code != 'khalti':
            return super()._apply_updates(payment_data)

        if payment_data.get('transaction_id'):
            self.provider_reference = payment_data['transaction_id']
        status = payment_data.get('status')
        if status in const.STATUS_MAPPING['done']:
            if payment_data.get('refunded'):
                self._set_error(_("Khalti reports this payment as refunded."))
            else:
                self._set_done()
        elif status in const.STATUS_MAPPING['pending']:
            self._set_pending()
        elif status in const.STATUS_MAPPING['cancel']:
            self._set_canceled(state_message=_("The Khalti payment was %s.", status.lower()))
        elif status in const.STATUS_MAPPING['error']:
            self._set_error(_("Khalti reports the payment as %s.", status.lower()))
        else:
            _logger.warning("Unknown Khalti status %s for transaction %s.", status, self.reference)
            self._set_error(_("Received an unknown payment status from Khalti: %s", status))
