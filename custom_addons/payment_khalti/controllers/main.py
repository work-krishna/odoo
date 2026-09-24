# Part of Odoo. See LICENSE file for full copyright and licensing details.

import pprint

from odoo import http
from odoo.http import request

from odoo.addons.payment.logging import get_payment_logger


_logger = get_payment_logger(__name__)


class KhaltiController(http.Controller):
    _return_url = '/payment/khalti/return'

    @http.route(_return_url, type='http', auth='public', methods=['GET'], csrf=False)
    def khalti_return(self, **data):
        """ Khalti's return redirect. Its query parameters are not signed, so they are only
        used to find the transaction; the state always comes from the lookup API. """
        _logger.info("Handling Khalti return with data:\n%s", pprint.pformat(data))
        tx_sudo = request.env['payment.transaction'].sudo()._search_by_reference('khalti', data)
        if tx_sudo:
            tx_sudo._khalti_sync_status()
        return request.redirect('/payment/status')
