# Part of Odoo. See LICENSE file for full copyright and licensing details.

import base64
import binascii
import json
import pprint

from odoo import http
from odoo.http import request

from odoo.addons.payment.controllers.post_processing import PaymentPostProcessing
from odoo.addons.payment.logging import get_payment_logger


_logger = get_payment_logger(__name__)


class EsewaController(http.Controller):
    _return_url = '/payment/esewa/return'
    _failure_url = '/payment/esewa/failure'

    @http.route(_return_url, type='http', auth='public', methods=['GET', 'POST'], csrf=False)
    def esewa_return(self, data=None, **kwargs):
        """ eSewa's success redirect: ``data`` is base64 JSON signed with the merchant key.

        The signed data is only used to find the transaction; its state comes from eSewa's
        status API, so a replayed or tampered redirect cannot mark a payment as done.
        """
        payload = self._decode(data)
        _logger.info("Handling eSewa return with data:\n%s", pprint.pformat(payload))
        tx_sudo = request.env['payment.transaction'].sudo()._search_by_reference('esewa', payload or {})
        if tx_sudo:
            if not tx_sudo._esewa_verify_signature(payload):
                _logger.warning("Invalid eSewa signature for transaction %s.", tx_sudo.reference)
            else:
                tx_sudo._esewa_sync_status()
        return request.redirect('/payment/status')

    @http.route(_failure_url, type='http', auth='public', methods=['GET', 'POST'], csrf=False)
    def esewa_failure(self, uuid=None, **kwargs):
        """ eSewa's failure redirect, which anyone can call: only for the payer's own
        transaction (the one monitored in their session), and only eSewa's status API
        decides whether it is canceled. """
        tx_sudo = request.env['payment.transaction'].sudo()._search_by_reference(
            'esewa', {'transaction_uuid': uuid},
        )
        if tx_sudo and tx_sudo.id == request.session.get(PaymentPostProcessing.MONITORED_TX_ID_KEY):
            tx_sudo._esewa_sync_status()
        elif tx_sudo:
            _logger.warning("eSewa failure redirect for transaction %s outside its payment session: ignored.",
                            tx_sudo.reference)
        return request.redirect('/payment/status')

    @staticmethod
    def _decode(data):
        if not data:
            return None
        try:
            return json.loads(base64.b64decode(data))
        except (binascii.Error, ValueError):
            _logger.warning("Could not decode the eSewa return data.")
            return None
