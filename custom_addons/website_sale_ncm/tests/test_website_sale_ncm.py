# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo.fields import Command
from odoo.tests import HttpCase, tagged

from odoo.addons.delivery_ncm.tests.common import NcmCommon


@tagged('post_install', '-at_install')
class TestWebsiteSaleNcm(NcmCommon, HttpCase):

    def test_districts_and_areas(self):
        Area = self.env['ncm.area']
        self.assertIn('KASKI', Area._ncm_frontend_districts())
        self.assertEqual(
            [area['label'] for area in Area._ncm_frontend_areas('kaski')],
            ['Bagbazar', 'Lakeside', 'Mahendrapul'],
        )
        self.assertEqual(Area._ncm_frontend_areas(''), [])

        areas = self.make_jsonrpc_request('/website_sale_ncm/areas', {'district': 'KATHMANDU'})
        self.assertEqual(
            sorted(area['label'] for area in areas),
            ['Asan', 'Bagbazar', 'Indrachowk', 'Koteshwor', 'Subidhanagar', 'Tinkune'],
        )

    def test_shared_area_names_show_their_branch(self):
        self.env['ncm.area'].create({'name': 'ASAN', 'branch_id': self.branch_tinkune.id})
        labels = [area['label'] for area in self.env['ncm.area']._ncm_frontend_areas('KATHMANDU')]
        self.assertIn('Asan (New Road branch)', labels)
        self.assertIn('Asan (Tinkune branch)', labels)

    def test_shop_hides_ncm_methods_that_cannot_ship(self):
        self.ncm.is_published = True
        order = self.env['sale.order'].create({
            'partner_id': self.customer.id,
            'website_id': self.env['website'].get_current_website().id,
            'order_line': [Command.create({'product_id': self.phone_product.id})],
        })
        self.assertIn(self.ncm, order._get_delivery_methods())

        self.ncm.ncm_from_branch_id = False  # The phone now has no pickup branch at all.
        self.assertNotIn(self.ncm, order._get_delivery_methods())

        self.phone_product.ncm_pickup_branch_id = self.branch_tinkune
        self.assertIn(self.ncm, order._get_delivery_methods())

        self.ncm.ncm_api_token = False
        self.assertNotIn(self.ncm, order._get_delivery_methods())

    def test_customer_sets_area_in_address_form(self):
        self.env['res.users'].create({
            'name': "NCM Portal User",
            'login': 'ncm_portal',
            'password': 'ncm_portal',
            'group_ids': [Command.set([self.env.ref('base.group_portal').id])],
        })
        self.start_tour('/my/address?address_type=delivery', 'website_sale_ncm_address_area', login='ncm_portal')
        address = self.env['res.partner'].search([('name', '=', 'Tour NCM Customer')])
        self.assertEqual(address.ncm_area_id, self.area_lakeside)
        self.assertEqual(address._ncm_get_dest_branch(), self.branch_pokhara)

    def test_order_page_shows_ncm_progress(self):
        order = self._confirmed_order()
        picking = order.picking_ids
        self._route_created_order()
        self._validate(picking)
        picking._ncm_set_current_status('Sent for Delivery')

        response = self.url_open(f'/my/orders/{order.id}?access_token={order._portal_ensure_token()}')
        self.assertEqual(response.status_code, 200)
        self.assertIn('Out for delivery', response.text)
        self.assertIn('To pay on delivery', response.text)
        self.assertIn('25,150.00', response.text)
