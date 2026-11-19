# Part of Odoo. See LICENSE file for full copyright and licensing details.

import hmac
import json
import logging

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class NcmWebhookController(http.Controller):

    @http.route(
        '/delivery_ncm/webhook/<string:secret>',
        type='http', auth='public', methods=['POST'], csrf=False, save_session=False,
    )
    def ncm_webhook(self, secret, **kwargs):
        """Receive NCM's order-status and order-comment webhooks (both use this address).

        The secret in the address identifies the delivery method; the call is only queued, and
        the order is then re-read from NCM's API rather than trusted from the payload.
        """
        carriers = request.env['delivery.carrier'].sudo().search([
            ('delivery_type', '=', 'ncm'), ('ncm_webhook_secret', '!=', False),
        ])
        carrier = next(
            (c for c in carriers if hmac.compare_digest(c.ncm_webhook_secret.encode(), secret.encode())),
            None,
        )
        if not carrier:
            return request.make_json_response({'success': False}, status=404)

        raw_body = request.httprequest.get_data(as_text=True) or ''
        try:
            payload = json.loads(raw_body) if raw_body.strip() else {}
        except ValueError:
            payload = request.httprequest.form.to_dict() or kwargs
        if not isinstance(payload, dict):
            payload = {'data': payload}
        carrier._ncm_receive_webhook(raw_body or json.dumps(payload), payload)
        return request.make_json_response({'success': True})
