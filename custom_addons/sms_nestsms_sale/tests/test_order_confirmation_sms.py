# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo.fields import Command
from odoo.tests import tagged

from odoo.addons.sms_nestsms.tests.common import NestSmsCommon
from odoo.addons.sms_nestsms.tools.sms_api import is_gsm7


@tagged('post_install', '-at_install')
class TestOrderConfirmationSms(NestSmsCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.product = cls.env['product.product'].create({
            'name': 'Redmi 13 Pro+', 'list_price': 25000.0, 'taxes_id': [Command.clear()],
        })

    def _order(self, partner=None):
        return self.env['sale.order'].create({
            'partner_id': (partner or self.customer).id,
            'order_line': [Command.create({'product_id': self.product.id, 'price_unit': 25000.0})],
        })

    def _sms(self, order):
        return self.env['sms.sms'].search([('mail_message_id', 'in', order.message_ids.ids)])

    def test_confirmation_texts_customer(self):
        order = self._order()
        order.action_confirm()

        sms = self._sms(order)
        self.assertEqual(len(sms), 1)
        self.assertEqual(sms.number, '+9779841234567')
        self.assertEqual(sms.body, f"Flagship-Store: Your order {order.name} (Rs. 25000.00) is confirmed. Thank you for shopping with us!")
        self.assertTrue(is_gsm7(sms.body))
        self.assertTrue(order.sms_confirmation_sent)

        self._send_queue()
        self.assertEqual(self.nestsms.calls[0]['payload']['to'], '9841234567')

    def test_once_per_order(self):
        order = self._order()
        order.action_confirm()
        order._action_cancel()
        order.action_draft()
        order.action_confirm()
        self.assertEqual(len(self._sms(order)), 1)

    def test_setting_off(self):
        self.company.sms_notify_order_confirmed = False
        order = self._order()
        order.action_confirm()
        self.assertFalse(self._sms(order))

    def test_no_mobile_no_sms(self):
        partner = self.env['res.partner'].create({'name': 'No Phone'})
        order = self._order(partner)
        order.action_confirm()
        self.assertEqual(order.state, 'sale')
        self.assertFalse(self._sms(order))
        self.assertFalse(order.sms_confirmation_sent)
