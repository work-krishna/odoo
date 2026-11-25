# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo.fields import Command
from odoo.tests import tagged

from odoo.addons.delivery_ncm.tests.common import NcmCommon, fake_response

RATES = {'NEW ROAD': '120.00', 'POKHARA': '170.00'}


@tagged('post_install', '-at_install')
class TestNcmPickup(NcmCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.ncm_collect = cls.env.ref('delivery_ncm.delivery_carrier_ncm_branch')
        cls.ncm_collect.write({
            'ncm_api_token': 'test-token',
            'ncm_from_branch_id': cls.branch_tinkune.id,
            'prod_environment': False,
        })

    def setUp(self):
        super().setUp()
        self.fake.routes[('GET', '/api/v1/shipping-rate')] = lambda kwargs: fake_response(
            200, {'charge': RATES.get(kwargs['params']['destination'], '100.00')},
        )

    def _collect_order(self, partner=None):
        order = self.env['sale.order'].create({
            'partner_id': (partner or self.customer).id,
            'order_line': [Command.create({
                'product_id': self.phone_product.id, 'price_unit': 25000.0,
            })],
        })
        order.set_delivery_line(self.ncm_collect, 100.0)
        return order

    def _location_names(self, order, search=None):
        # Like the shop's route, pass the address country with a search (website_sale_collect,
        # when installed, otherwise looks it up by GeoIP, which needs an HTTP request).
        country = self.env.ref('base.np') if search else None
        locations = order._get_pickup_locations(search, country)['pickup_locations']
        return [location['name'] for location in locations]

    def test_collect_service_uses_locations(self):
        self.assertTrue(self.ncm_collect.ncm_use_locations)
        self.assertFalse(self.ncm.ncm_use_locations)

    def test_branches_near_customer(self):
        order = self._collect_order()
        locations = order._get_pickup_locations()['pickup_locations']
        self.assertEqual([location['name'] for location in locations], ['NCM Pokhara'])
        self.assertEqual(locations[0]['id'], self.branch_pokhara.id)
        self.assertEqual(locations[0]['country_code'], 'NP')
        self.assertEqual(locations[0]['city'], 'Kaski')
        self.assertLessEqual(
            {'id', 'name', 'street', 'city', 'zip_code', 'country_code', 'latitude', 'longitude', 'opening_hours'},
            set(locations[0]),
        )

    def test_search_by_town_district_or_area(self):
        order = self._collect_order()
        # SANKHU is a 'Logistics' point: not offered for collection.
        self.assertEqual(set(self._location_names(order, 'kathmandu')), {'NCM Tinkune', 'NCM New Road'})
        self.assertEqual(self._location_names(order, 'Koteshwor')[0], 'NCM Tinkune')
        self.assertEqual(self._location_names(order, 'asan')[0], 'NCM New Road')
        # A postal code is not searchable: fall back to the delivery address.
        self.assertEqual(self._location_names(order, '33700'), ['NCM Pokhara'])
        self.assertIn('error', order._get_pickup_locations('Nowhere', self.env.ref('base.np')))

    def test_price_before_a_branch_is_chosen(self):
        stranger = self.env['res.partner'].create({'name': 'Hari', 'city': 'Somewhere', 'phone': '9800000001'})
        order = self._collect_order(stranger)
        rate = self.ncm_collect.rate_shipment(order)
        self.assertTrue(rate['success'], rate.get('error_message'))
        self.assertEqual(rate['price'], 100.0)
        params = self.fake.calls_to('/api/v1/shipping-rate')[-1]['params']
        self.assertEqual((params['destination'], params['type']), ('TINKUNE', 'D2B'))

    def test_collect_at_branch_order(self):
        order = self._collect_order()
        order._ncm_set_pickup_branch(self.branch_newroad)
        self.assertEqual(order.pickup_location_data['id'], self.branch_newroad.id, "The branch survives re-pricing.")
        self.assertEqual(order.order_line.filtered('is_delivery').price_unit, 120.0)

        order.action_confirm()
        shipping = order.partner_shipping_id
        self.assertTrue(shipping.is_pickup_location)
        self.assertEqual((shipping.name, shipping.parent_id), ('NCM New Road', self.customer))

        picking = order.picking_ids
        self.assertEqual(picking.ncm_dest_branch_id, self.branch_newroad)
        self.assertEqual(picking.ncm_cod_amount, 25120.0)
        self._route_created_order()
        self._validate(picking)
        payload = self._created_payload()
        # The customer, not the branch contact Odoo created, is sent to NCM.
        self.assertEqual(
            (payload['name'], payload['phone'], payload['address'], payload['branch'], payload['delivery_type']),
            ('Sita Gurung', '9841234567', 'Lakeside Road 6, Pokhara', 'NEW ROAD', 'Door2Branch'),
        )

    def test_customer_emails(self):
        self.customer.email = 'sita@example.com'

        def sent(subject_part):
            return picking.message_ids.filtered(lambda m: subject_part in (m.subject or ''))

        picking = self._confirmed_order().picking_ids
        self._route_created_order()
        self._validate(picking)
        picking._ncm_set_current_status('Sent for Delivery')
        self.assertFalse(sent('on its way'), "Emails are off by default.")

        picking.ncm_state = 'pickup'
        self.ncm.ncm_notify_customer = True
        picking._ncm_set_current_status('Sent for Delivery')
        picking._ncm_set_current_status('Sent for Delivery')
        message = sent('on its way')
        self.assertEqual(len(message), 1)
        self.assertIn(self.customer, message.partner_ids)
        self.assertIn('25,150.00', message.body)
        picking._ncm_set_current_status('Delivered')
        self.assertEqual(len(sent('was delivered')), 1)
