# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo.tests import tagged

from odoo.addons.delivery_ncm.tests.common import NcmCommon, fake_response

STATUS_HISTORY = [
    {'orderid': 747, 'status': 'Sent for Delivery', 'added_time': '2026-11-20T13:22:21.033595+05:45'},
    {'orderid': 747, 'status': 'Pickup Complete', 'added_time': '2026-11-20T09:17:25.326792+05:45'},
    {'orderid': 747, 'status': 'Pickup Order Created', 'added_time': '2026-11-19T11:32:18.149352+05:45'},
]
COMMENTS = [
    {'orderid': 747, 'comments': "Customer asked to deliver after 4 pm", 'addedBy': 'NCM Staff',
     'added_time': '2026-11-20T12:00:00.000000+05:45'},
    {'orderid': 747, 'comments': "Fragile, handle with care", 'addedBy': 'Vendor',
     'added_time': '2026-11-19T11:40:00.000000+05:45'},
]


@tagged('post_install', '-at_install')
class TestNcmSync(NcmCommon):

    def setUp(self):
        super().setUp()
        order = self._confirmed_order()
        self.picking = order.picking_ids
        self._route_created_order()
        self._validate(self.picking)
        self.fake.calls.clear()
        self.fake.routes.update({
            ('GET', '/api/v1/order/status'): fake_response(200, STATUS_HISTORY),
            ('GET', '/api/v1/order/comment'): fake_response(200, COMMENTS),
            ('GET', '/api/v1/order/getbulkcomments'): fake_response(200, COMMENTS),
        })

    def _route_bulk_status(self, status):
        self.fake.routes[('POST', '/api/v1/orders/statuses')] = fake_response(
            200, {'result': {'747': status}, 'errors': []},
        )

    def _staff_notes(self):
        return self.picking.message_ids.filtered(lambda m: 'deliver after 4 pm' in (m.body or ''))

    def test_status_change_refreshes_order(self):
        self._route_bulk_status('Sent for Delivery')
        self.env['delivery.carrier']._ncm_cron_sync_status()

        self.assertEqual(self.picking.ncm_state, 'out_for_delivery')
        self.assertEqual(self.picking.ncm_status, 'Sent for Delivery')
        self.assertEqual(str(self.picking.ncm_status_date), '2026-11-20 07:37:21')  # 13:22 NPT in UTC
        self.assertEqual(self.picking.ncm_status_ids.sorted('date', reverse=True).mapped('status'), [
            'Sent for Delivery', 'Pickup Complete', 'Pickup Order Created',
        ])
        self.assertEqual(len(self.picking.ncm_comment_ids), 2)
        self.assertEqual(len(self._staff_notes()), 1, "Only NCM staff comments go to the chatter.")

        # Nothing changed at NCM: one bulk call, no per-order reads.
        self.fake.calls.clear()
        self.env['delivery.carrier']._ncm_cron_sync_status()
        self.assertEqual([call['path'] for call in self.fake.calls], ['/api/v1/orders/statuses'])
        self.assertEqual(len(self.picking.ncm_status_ids), 3)

    def test_final_orders_are_not_polled(self):
        self._route_bulk_status('Delivered')
        self.fake.routes[('GET', '/api/v1/order/status')] = fake_response(200, [
            {'orderid': 747, 'status': 'Delivered', 'added_time': '2026-11-21T10:00:00+05:45'},
        ] + STATUS_HISTORY)
        self.env['delivery.carrier']._ncm_cron_sync_status()
        self.assertEqual(self.picking.ncm_state, 'delivered')
        self.assertTrue(self.picking.message_ids.filtered(lambda m: 'Delivered' in (m.body or '')))

        self.fake.calls.clear()
        self.env['delivery.carrier']._ncm_cron_sync_status()
        self.assertFalse(self.fake.calls)

    def test_cancel_request_waits_for_ncm(self):
        self.fake.routes[('POST', '/api/v1/comment')] = fake_response(200, {'message': "ok"})
        self.picking.cancel_shipment()
        self._route_bulk_status('Sent for Delivery')
        self.env['delivery.carrier']._ncm_cron_sync_status()
        self.assertEqual(self.picking.ncm_state, 'cancel_requested')
        self.assertEqual(self.picking.ncm_status, 'Sent for Delivery')

    def test_bulk_comments_are_stored_once(self):
        Carrier = self.env['delivery.carrier']
        Carrier._ncm_cron_sync_comments()
        Carrier._ncm_cron_sync_comments()
        self.assertEqual(len(self.picking.ncm_comment_ids), 2)
        self.assertEqual(len(self._staff_notes()), 1)

    def test_manual_refresh(self):
        self.picking.action_ncm_refresh()
        self.assertEqual(self.picking.ncm_state, 'out_for_delivery')

    def test_message_wizard(self):
        self.fake.routes[('POST', '/api/v1/comment')] = fake_response(200, {'message': "Comment successfully created"})
        wizard = self.env['ncm.comment.wizard'].create({'picking_id': self.picking.id, 'message': "  Call before coming  "})
        wizard.action_send()
        self.assertEqual(self.fake.calls_to('/api/v1/comment')[0]['json'], {'orderid': '747', 'comments': "Call before coming"})
        self.assertTrue(self.picking.message_ids.filtered(lambda m: 'Call before coming' in (m.body or '')))
