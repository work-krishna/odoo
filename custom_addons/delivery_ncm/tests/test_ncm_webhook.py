# Part of Odoo. See LICENSE file for full copyright and licensing details.

import json

from odoo.tests import HttpCase, tagged

from odoo.addons.delivery_ncm.tests.common import NcmCommon, fake_response


@tagged('post_install', '-at_install')
class TestNcmWebhook(NcmCommon, HttpCase):

    def _post(self, secret, payload):
        return self.url_open(
            f'/delivery_ncm/webhook/{secret}',
            data=json.dumps(payload),
            headers={'Content-Type': 'application/json'},
        )

    def test_webhook_queues_then_refreshes(self):
        picking = self._confirmed_order().picking_ids
        self._route_created_order()
        self._validate(picking)
        secret = self.ncm.sudo().ncm_webhook_secret

        response = self._post(secret, {
            'event': 'order.status.changed', 'order_id': 747, 'status': 'Delivered',
            'timestamp': '2026-11-21T10:00:00+05:45',
        })
        self.assertEqual(response.status_code, 200)
        event = self.env['ncm.webhook.event'].search([('ncm_order_id', '=', 747)])
        self.assertEqual(event.state, 'pending')
        self.assertEqual(picking.ncm_state, 'created', "The payload itself is not trusted.")

        self.fake.routes.update({
            ('GET', '/api/v1/order/status'): fake_response(200, [
                {'orderid': 747, 'status': 'Delivered', 'added_time': '2026-11-21T10:00:00+05:45'},
            ]),
            # What NCM really answers for an order without comments.
            ('GET', '/api/v1/order/comment'): fake_response(200, {'detail': "No comments found"}),
        })
        self.env['delivery.carrier']._ncm_cron_process_webhooks()
        self.assertEqual(event.state, 'done')
        self.assertEqual(picking.ncm_state, 'delivered')

    def test_wrong_secret_and_test_calls(self):
        self.assertEqual(self._post('not-the-secret', {'order_id': 1}).status_code, 404)

        secret = self.ncm.sudo().ncm_webhook_secret
        response = self._post(secret, {
            'event': 'order.status.changed', 'order_id': 'TEST-123456', 'status': 'In Transit',
            'timestamp': '2024-01-01T12:00:00+05:45', 'test': True,
        })
        self.assertEqual(response.status_code, 200)
        event = self.env['ncm.webhook.event'].search([], limit=1)
        self.assertEqual((event.state, event.note), ('ignored', 'Test call'))

    def test_unknown_order_is_retried_then_dropped(self):
        secret = self.ncm.sudo().ncm_webhook_secret
        self._post(secret, {'orderid': 999999, 'comments': 'Hello'})
        event = self.env['ncm.webhook.event'].search([('ncm_order_id', '=', 999999)])
        Carrier = self.env['delivery.carrier']
        Carrier._ncm_cron_process_webhooks()
        self.assertEqual((event.state, event.attempts), ('pending', 1))
        self.env.cr.execute(
            "UPDATE ncm_webhook_event SET create_date = now() at time zone 'UTC' - interval '3 hours' WHERE id = %s",
            [event.id],
        )
        event.invalidate_recordset()
        Carrier._ncm_cron_process_webhooks()
        self.assertEqual(event.state, 'ignored')
