# Part of Odoo. See LICENSE file for full copyright and licensing details.

import json

from odoo.fields import Command
from odoo.tests import tagged

from odoo.addons.delivery_ncm.tests.common import NcmCommon


@tagged('post_install', '-at_install')
class TestNcmCashOnDelivery(NcmCommon):
    """What the shop's payment status page does after a cash-on-delivery checkout."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.cod_provider = cls.env.ref('delivery.payment_provider_cod')
        cls.cod_provider.write({'state': 'test', 'company_id': cls.env.company.id})
        cls.env['delivery.carrier'].search([('delivery_type', '=', 'ncm')]).write({
            'allow_cash_on_delivery': True,
            'ncm_api_token': 'test-token',
            'ncm_from_branch_id': cls.branch_tinkune.id,
        })

    def _checkout(self, carrier, pickup_branch=None):
        order = self.env['sale.order'].create({
            'partner_id': self.customer.id,
            'order_line': [Command.create({'product_id': self.phone_product.id, 'price_unit': 25000.0})],
        })
        rate = carrier.rate_shipment(order)
        self.assertTrue(rate['success'], rate.get('error_message'))
        order.set_delivery_line(carrier, rate['price'])
        if pickup_branch:
            order._set_pickup_location(json.dumps(pickup_branch._ncm_pickup_location_values()))
        tx = self.env['payment.transaction'].sudo().create({
            'provider_id': self.cod_provider.id,
            'payment_method_id': self.env.ref('delivery.payment_method_cash_on_delivery').id,
            'reference': order.name,
            'amount': order.amount_total,
            'currency_id': order.currency_id.id,
            'partner_id': self.customer.id,
            'operation': 'online_redirect',
            'sale_order_ids': [Command.set(order.ids)],
        })
        tx._set_pending()
        tx._post_process()
        return order

    def test_home_delivery(self):
        order = self._checkout(self.ncm)
        self.assertEqual(order.state, 'sale')
        self.assertEqual(order.picking_ids.ncm_cod_amount, 25150.0)

    def test_collect_at_branch(self):
        collect = self.env.ref('delivery_ncm.delivery_carrier_ncm_branch')
        order = self._checkout(collect, pickup_branch=self.branch_pokhara)
        self.assertEqual(order.state, 'sale')
        self.assertEqual(order.picking_ids.ncm_dest_branch_id, self.branch_pokhara)
