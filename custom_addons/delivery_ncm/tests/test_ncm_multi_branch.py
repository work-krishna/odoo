# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo.exceptions import UserError
from odoo.fields import Command
from odoo.tests import tagged

from odoo.addons.delivery_ncm.tests.common import NcmCommon, fake_response

RATES = {('TINKUNE', 'POKHARA'): '150.00', ('NEW ROAD', 'POKHARA'): '160.00'}


@tagged('post_install', '-at_install')
class TestNcmMultiBranch(NcmCommon):
    """Products leaving from different NCM branches ship as one parcel per branch."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.case_product = cls.env['product.product'].create({
            'name': 'Phone case',
            'type': 'consu',
            'list_price': 500.0,
            'weight': 0.1,
            'taxes_id': [Command.clear()],
            'ncm_pickup_branch_id': cls.branch_newroad.id,
        })
        cls.warehouse = cls.env['stock.warehouse'].search([('company_id', '=', cls.env.company.id)], limit=1)

    def setUp(self):
        super().setUp()
        self.fake.routes[('GET', '/api/v1/shipping-rate')] = lambda kwargs: fake_response(
            200, {'charge': RATES[(kwargs['params']['creation'], kwargs['params']['destination'])]},
        )

    def _mixed_order(self):
        order = self.env['sale.order'].create({
            'partner_id': self.customer.id,
            'order_line': [
                Command.create({'product_id': self.phone_product.id, 'price_unit': 25000.0}),
                Command.create({'product_id': self.case_product.id, 'price_unit': 500.0}),
            ],
        })
        rate = self.ncm.rate_shipment(order)
        order.set_delivery_line(self.ncm, rate['price'])
        return order, rate

    def test_pickup_branch_precedence(self):
        pickup_branch = self.ncm._ncm_pickup_branch_for
        self.assertEqual(pickup_branch(self.case_product, self.warehouse), self.branch_newroad)  # product
        self.assertEqual(pickup_branch(self.phone_product, self.warehouse), self.branch_tinkune)  # method default
        self.warehouse.ncm_pickup_branch_id = self.branch_pokhara
        self.assertEqual(pickup_branch(self.phone_product, self.warehouse), self.branch_pokhara)  # warehouse
        self.assertEqual(pickup_branch(self.case_product, self.warehouse), self.branch_newroad)  # product wins

    def test_quote_adds_up_the_parcels(self):
        order, rate = self._mixed_order()
        self.assertTrue(rate['success'], rate.get('error_message'))
        self.assertEqual(rate['price'], 310.0)
        creations = sorted(call['params']['creation'] for call in self.fake.calls_to('/api/v1/shipping-rate'))
        self.assertEqual(creations, ['NEW ROAD', 'TINKUNE'], "One quote per pickup branch, then cached.")
        self.assertEqual(order.ncm_rate_breakdown, {
            str(self.branch_tinkune.id): 150.0,
            str(self.branch_newroad.id): 160.0,
        })

    def test_order_ships_as_one_parcel_per_branch(self):
        order, _rate = self._mixed_order()
        order.action_confirm()
        pickings = order.picking_ids
        self.assertEqual(len(pickings), 2)
        by_branch = {picking.ncm_from_branch_id: picking for picking in pickings}
        phone_parcel = by_branch[self.branch_tinkune]
        case_parcel = by_branch[self.branch_newroad]
        self.assertEqual(phone_parcel.move_ids.product_id, self.phone_product)
        self.assertEqual(case_parcel.move_ids.product_id, self.case_product)
        self.assertFalse(phone_parcel.ncm_branch_conflict)
        # Each parcel collects for its own items plus its own delivery quote.
        self.assertEqual(phone_parcel.ncm_cod_amount, 25150.0)
        self.assertEqual(case_parcel.ncm_cod_amount, 660.0)
        self.assertAlmostEqual(phone_parcel.ncm_cod_amount + case_parcel.ncm_cod_amount, order.amount_total)

        self._route_created_order(order_id=801)
        self._validate(phone_parcel)
        self._route_created_order(order_id=802)
        self._validate(case_parcel)
        payloads = [call['json'] for call in self.fake.calls_to('/api/v1/order/create')]
        self.assertEqual(
            [(payload['fbranch'], payload['cod_charge'], payload['package']) for payload in payloads],
            [('TINKUNE', '25150', 'Redmi 13 Pro+ x1'), ('NEW ROAD', '660', 'Phone case x1')],
        )
        self.assertEqual(payloads[0]['vref_id'], order.name)
        self.assertTrue(payloads[1]['vref_id'].startswith(f'{order.name}-'))
        self.assertEqual((phone_parcel.carrier_tracking_ref, case_parcel.carrier_tracking_ref), ('801', '802'))

    def test_product_without_pickup_branch(self):
        self.ncm.ncm_from_branch_id = False
        order = self.env['sale.order'].create({
            'partner_id': self.customer.id,
            'order_line': [Command.create({'product_id': self.phone_product.id})],
        })
        rate = self.ncm.rate_shipment(order)
        self.assertFalse(rate['success'])
        self.assertIn('No NCM pickup branch for Redmi 13 Pro+', rate['error_message'])
        self.assertFalse(self.ncm._ncm_is_ready_for_order(order))

        self.phone_product.ncm_pickup_branch_id = self.branch_tinkune
        self.assertTrue(self.ncm._ncm_is_ready_for_order(order))
        self.assertTrue(self.ncm.rate_shipment(order)['success'])

    def test_hand_made_mixed_transfer_is_refused(self):
        picking_type = self.warehouse.out_type_id
        source = picking_type.default_location_src_id
        customers = self.env.ref('stock.stock_location_customers')
        picking = self.env['stock.picking'].create({
            'picking_type_id': picking_type.id,
            'partner_id': self.customer.id,
            'carrier_id': self.ncm.id,
            'location_id': source.id,
            'location_dest_id': customers.id,
            'move_ids': [
                Command.create({
                    'product_id': product.id,
                    'product_uom_qty': 1,
                    'location_id': source.id,
                    'location_dest_id': customers.id,
                })
                for product in (self.phone_product, self.case_product)
            ],
        })
        self.assertIn('TINKUNE', picking.ncm_branch_conflict)
        self.assertIn('NEW ROAD', picking.ncm_branch_conflict)
        with self.assertRaises(UserError) as capture:
            self.ncm._ncm_send_picking(picking)
        self.assertIn('several NCM pickup branches', str(capture.exception))
        self.assertFalse(self.fake.calls_to('/api/v1/order/create'))
