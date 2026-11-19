# Part of Odoo. See LICENSE file for full copyright and licensing details.

import requests

from odoo.exceptions import UserError
from odoo.fields import Command
from odoo.tests import Form, tagged

from odoo.addons.delivery_ncm.tests.common import NcmCommon, fake_response


@tagged('post_install', '-at_install')
class TestNcmShipping(NcmCommon):

    # Rates ---------------------------------------------------------------------------------

    def test_rate_uses_ncm_quote_once_per_route(self):
        order = self._confirmed_order()
        rate = self.ncm.rate_shipment(order)
        self.assertTrue(rate['success'], rate.get('error_message'))
        self.assertEqual(rate['price'], 150.0)
        self.assertEqual(self.ncm.rate_shipment(order)['price'], 150.0)
        calls = self.fake.calls_to('/api/v1/shipping-rate')
        self.assertEqual(len(calls), 1, "The second quote for the same route comes from the cache.")
        self.assertEqual(calls[0]['params'], {'creation': 'TINKUNE', 'destination': 'POKHARA', 'type': 'Pickup/Collect'})

    def test_rate_parameters_follow_service(self):
        self.ncm.ncm_delivery_type = 'Door2Branch'
        order = self._confirmed_order()
        self.assertTrue(self.ncm.rate_shipment(order)['success'])
        call = self.fake.calls_to('/api/v1/shipping-rate')[0]
        self.assertEqual(call['params'], {'creation': 'TINKUNE', 'destination': 'POKHARA', 'type': 'D2B'})

    def test_rate_without_known_branch(self):
        stranger = self.env['res.partner'].create({'name': 'Hari', 'city': 'Somewhere'})
        order = self.env['sale.order'].create({
            'partner_id': stranger.id,
            'order_line': [Command.create({'product_id': self.phone_product.id})],
        })
        rate = self.ncm.rate_shipment(order)
        self.assertFalse(rate['success'])
        self.assertIn('NCM delivery area', rate['error_message'])
        self.assertFalse(self.fake.calls)

    def test_rate_ncm_error_is_reported(self):
        self.fake.routes[('GET', '/api/v1/shipping-rate')] = fake_response(500, text="DoesNotExist at /x\nBranch matching query does not exist.")
        order = self.env['sale.order'].create({
            'partner_id': self.customer.id,
            'order_line': [Command.create({'product_id': self.phone_product.id})],
        })
        rate = self.ncm.rate_shipment(order)
        self.assertFalse(rate['success'])
        self.assertIn('Branch matching query does not exist', rate['error_message'])

    def test_rate_extra_weight(self):
        self.ncm.ncm_extra_kg_price = 20.0
        order = self.env['sale.order'].create({
            'partner_id': self.customer.id,
            'order_line': [Command.create({'product_id': self.phone_product.id, 'product_uom_qty': 5})],
        })
        # 5 x 0.4 kg = 2 kg: one kg above the first.
        self.assertEqual(self.ncm.rate_shipment(order)['price'], 170.0)

    # Sending -------------------------------------------------------------------------------

    def test_validation_creates_ncm_order(self):
        order = self._confirmed_order()
        picking = order.picking_ids
        self.assertEqual(picking.carrier_id, self.ncm)
        self.assertEqual(picking.ncm_dest_branch_id, self.branch_pokhara)
        self.assertEqual(picking.ncm_cod_amount, 25150.0)
        self._route_created_order()

        self._validate(picking)

        payload = self._created_payload()
        self.assertEqual(payload, {
            'name': 'Sita Gurung',
            'phone': '9841234567',
            'phone2': '',
            'cod_charge': '25150',
            'address': 'Lakeside Road 6, Pokhara',
            'fbranch': 'TINKUNE',
            'branch': 'POKHARA',
            'package': 'Redmi 13 Pro+ x1',
            'vref_id': order.name,
            'instruction': '',
            'delivery_type': 'Door2Door',
            'weight': '1',
        })
        self.assertEqual(picking.state, 'done')
        self.assertEqual(picking.carrier_tracking_ref, '747')
        self.assertEqual(picking.ncm_order_id, 747)
        self.assertEqual(picking.ncm_state, 'created')
        self.assertEqual(picking.ncm_status, 'Pickup Order Created')
        self.assertEqual(picking.ncm_delivery_charge, 99.0)
        self.assertEqual(picking.carrier_price, 99.0)
        self.assertEqual(picking.ncm_vref, order.name)
        self.assertEqual(picking.ncm_track_id, 'B79F9E65E673439')
        log =self.env['ncm.api.log'].search([('picking_res_id', '=', picking.id)])
        self.assertEqual((log.state, log.ncm_order_id, log.environment), ('created', 747, 'demo'))
        label = self.env['ir.attachment'].search([
            ('res_model', '=', 'stock.picking'), ('res_id', '=', picking.id), ('name', '=', 'LabelShipping-ncm-747.pdf'),
        ])
        self.assertTrue(label)

    def test_prepaid_order_collects_nothing(self):
        order = self._confirmed_order()
        provider = self.env['payment.provider'].create({'name': "Paid online", 'code': 'none'})
        self.env['payment.transaction'].create({
            'provider_id': provider.id,
            'payment_method_id': self.env['payment.method'].search([], limit=1).id,
            'reference': f'{order.name}-paid',
            'amount': order.amount_total,
            'currency_id': order.currency_id.id,
            'partner_id': self.customer.id,
            'sale_order_ids': [Command.set(order.ids)],
            'state': 'done',
        })
        picking = order.picking_ids
        self.assertEqual(picking.ncm_cod_amount, 0.0)
        self._route_created_order()
        self._validate(picking)
        self.assertEqual(self._created_payload()['cod_charge'], '0')

    def test_ncm_refusal_blocks_validation(self):
        picking = self._confirmed_order().picking_ids
        self.fake.routes[('POST', '/api/v1/order/create')] = fake_response(
            400, {'Error': {'phone': 'Invalid Phone Number'}},
        )
        # Odoo's assertRaises (unlike assertRaisesRegex) rolls back like a failed request would.
        with self.assertRaises(UserError) as capture:
            self._validate(picking)
        self.assertIn('Invalid Phone Number', str(capture.exception))
        picking.invalidate_recordset()
        self.assertNotEqual(picking.state, 'done')
        self.assertFalse(picking.carrier_tracking_ref)

    def test_missing_data_is_listed_before_calling_ncm(self):
        picking = self._confirmed_order().picking_ids
        picking.partner_id.phone = False
        picking.ncm_dest_branch_id = False
        with self.assertRaises(UserError) as capture:
            self._validate(picking)
        self.assertRegex(str(capture.exception), "destination branch.*phone number")
        self.assertFalse(self.fake.calls_to('/api/v1/order/create'))

    def test_unknown_outcome_blocks_until_checked(self):
        """A timed-out creation must never be retried blindly: NCM may hold the order."""
        picking = self._confirmed_order().picking_ids
        self.fake.routes[('POST', '/api/v1/order/create')] = requests.exceptions.ReadTimeout()

        # Called directly, without assertRaises' savepoint: the log is written through another
        # cursor, which in tests shares (and would be rolled back with) the test transaction.
        for _attempt in range(2):
            try:
                self.ncm._ncm_send_picking(picking)
            except UserError as e:
                error = str(e)
            else:
                self.fail("Sending should have been refused.")
        self.assertIn('vendor portal', error)
        self.assertEqual(len(self.fake.calls_to('/api/v1/order/create')), 1, "The second try must not call NCM.")
        log = self.env['ncm.api.log'].search([('picking_res_id', '=', picking.id)])
        self.assertEqual(log.state, 'uncertain')
        picking.invalidate_recordset(['ncm_needs_check'])
        self.assertTrue(picking.ncm_needs_check)

        # Staff found the order in NCM's portal and link it.
        self.fake.routes[('GET', '/api/v1/order')] = fake_response(200, {
            'orderid': 555, 'cod_charge': '25150.00', 'delivery_charge': '120.00',
            'last_delivery_status': 'Pickup Order Created', 'payment_status': 'Pending',
        })
        picking.ncm_order_id = 555
        picking.action_ncm_link_order()
        picking.invalidate_recordset(['ncm_needs_check'])
        self.assertFalse(picking.ncm_needs_check)
        self._validate(picking)
        self.assertEqual(len(self.fake.calls_to('/api/v1/order/create')), 1)
        self.assertEqual(picking.carrier_tracking_ref, '555')
        self.assertEqual(picking.ncm_delivery_charge, 120.0)

    def test_force_create_after_unknown_outcome(self):
        picking = self._confirmed_order().picking_ids
        self.fake.routes[('POST', '/api/v1/order/create')] = requests.exceptions.ReadTimeout()
        try:
            self.ncm._ncm_send_picking(picking)
        except UserError:
            pass
        self._route_created_order(order_id=812)
        picking.action_ncm_force_create()
        self.assertEqual(picking.state, 'done')
        self.assertEqual(picking.carrier_tracking_ref, '812')
        self.assertEqual(len(self.fake.calls_to('/api/v1/order/create')), 2)

    def test_order_created_before_a_rollback_is_reused(self):
        picking = self._confirmed_order().picking_ids
        # What survives when NCM created the order but Odoo then rolled the validation back.
        self.ncm._ncm_record_attempt(picking, {'vref_id': 'S00042', 'package': 'Phone x1', 'weight': '1'}, 'created', order_id=901)
        self._route_created_order(order_id=901)
        self._validate(picking)
        self.assertFalse(self.fake.calls_to('/api/v1/order/create'))
        self.assertEqual(picking.carrier_tracking_ref, '901')
        self.assertEqual(picking.ncm_vref, 'S00042')

    def test_cancel_then_send_again(self):
        picking = self._confirmed_order().picking_ids
        self._route_created_order()
        self._validate(picking)
        self.fake.routes[('POST', '/api/v1/comment')] = fake_response(200, {'message': "Comment successfully created"})

        picking.cancel_shipment()

        self.assertEqual(self.fake.calls_to('/api/v1/comment')[0]['json']['orderid'], '747')
        self.assertFalse(picking.carrier_tracking_ref)
        self.assertEqual(picking.ncm_state, 'cancel_requested')
        self.assertTrue(picking.activity_ids.filtered(lambda a: '747' in (a.summary or '')))
        self.assertEqual(picking.ncm_dest_branch_id, self.branch_pokhara)

        self._route_created_order(order_id=748)
        picking.send_to_shipper()
        self.assertEqual(len(self.fake.calls_to('/api/v1/order/create')), 2)
        self.assertEqual(picking.carrier_tracking_ref, '748')
        self.assertEqual(picking.ncm_state, 'created')

    def test_second_shipment_does_not_collect_again(self):
        order = self._confirmed_order(quantity=2)
        picking = order.picking_ids
        self._route_created_order()
        picking.move_ids.quantity = 1
        picking.move_ids.picked = True
        action = picking.button_validate()
        Form.from_action(self.env, action).save().process()
        backorder = order.picking_ids - picking
        self.assertEqual(len(backorder), 1)
        self.assertEqual(picking.ncm_cod_amount, order.amount_total)
        backorder.invalidate_recordset(['ncm_cod_amount'])
        backorder._compute_ncm_cod_amount()
        self.assertEqual(backorder.ncm_cod_amount, 0.0)
        self.assertEqual(backorder._ncm_reference(), f"{order.name}-{backorder.name.rsplit('/', 1)[-1]}")
