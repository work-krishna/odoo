# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import http
from odoo.http import request

from odoo.addons.payment.logging import get_payment_logger


_logger = get_payment_logger(__name__)


class ConnectipsController(http.Controller):
    """ Register these two URLs with NCHL as the merchant's success and failure URLs. """
    _return_url = '/payment/connectips/return'
    _failure_url = '/payment/connectips/failure'

    @http.route([_return_url, _failure_url], type='http', auth='public', methods=['GET', 'POST'], csrf=False)
    def connectips_return(self, TXNID=None, **kwargs):
        """ connectIPS only appends TXNID; the outcome always comes from the validation API. """
        _logger.info("Handling connectIPS return for TXNID %s", TXNID)
        tx_sudo = request.env['payment.transaction'].sudo()._search_by_reference('connectips', {'TXNID': TXNID})
        if tx_sudo:
            tx_sudo._connectips_sync_status()
            if request.httprequest.path == self._failure_url and tx_sudo.state in ('draft', 'pending'):
                tx_sudo._set_canceled(state_message="The payment was canceled on connectIPS.")
        return request.redirect('/payment/status')
