# Part of Odoo. See LICENSE file for full copyright and licensing details.

import pprint

from odoo import _, http
from odoo.exceptions import ValidationError
from odoo.http import request

from odoo.addons.payment.logging import get_payment_logger


_logger = get_payment_logger(__name__)


class FonepayController(http.Controller):
    _process_url = '/payment/fonepay/process'
    _poll_url = '/payment/fonepay/poll'

    @http.route(_process_url, type='http', auth='public', methods=['POST'], csrf=False)
    def fonepay_process_transaction(self, **post):
        """ Move the transaction to the 'pending' state now that its QR code is displayed.

        The customer is then redirected to the payment status page, from which the QR code is
        displayed and the payment status is polled until the customer completes the payment.

        :param dict post: The data forwarded by the redirect form, holding the transaction
                           reference.
        :return: A redirection to the payment status page.
        """
        _logger.info("Handling Fonepay processing with data:\n%s", pprint.pformat(post))
        request.env['payment.transaction'].sudo()._process('fonepay', post)
        return request.redirect('/payment/status')

    @http.route(_poll_url, type='jsonrpc', auth='public')
    def fonepay_poll_status(self, reference):
        """ Check the QR payment status with Fonepay and update the transaction accordingly.

        This is called repeatedly by the client while the QR code is displayed, since Fonepay
        notifies payment completion through a WebSocket connection rather than a webhook that
        Odoo could receive directly.

        :param str reference: The reference of the transaction to check.
        :return: The current state of the transaction.
        :rtype: dict
        """
        tx_sudo = request.env['payment.transaction'].sudo().search([
            ('reference', '=', reference), ('provider_code', '=', 'fonepay'),
        ], limit=1)
        if not tx_sudo:
            raise ValidationError(_("The Fonepay transaction with reference %s does not exist.", reference))

        tx_sudo._fonepay_check_qr_status()
        return {'state': tx_sudo.state}
