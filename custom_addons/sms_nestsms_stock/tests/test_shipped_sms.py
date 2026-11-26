# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo.fields import Command
from odoo.tests import tagged

from odoo.addons.sms_nestsms.tests.common import NestSmsCommon
from odoo.addons.sms_nestsms.tools.sms_api import is_gsm7


@tagged('post_install', '-at_install')
class TestShippedSms(NestSmsCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company.stock_text_confirmation = True
        cls.warehouse = cls.env['stock.warehouse'].search([('company_id', '=', cls.company.id)], limit=1)
        cls.product = cls.env['product.product'].create({'name': 'Redmi 13 Pro+', 'type': 'consu'})
        cls.our_template = cls.env.ref('sms_nestsms_stock.sms_template_shipped')

    def _delivery(self, **values):
        picking = self.env['stock.picking'].create({
            'picking_type_id': self.warehouse.out_type_id.id,
            'partner_id': self.customer.id,
            'origin': 'S00123',
            'location_id': self.warehouse.lot_stock_id.id,
            'location_dest_id': self.env.ref('stock.stock_location_customers').id,
            'move_ids': [Command.create({
                'product_id': self.product.id,
                'product_uom_qty': 1,
                'location_id': self.warehouse.lot_stock_id.id,
                'location_dest_id': self.env.ref('stock.stock_location_customers').id,
            })],
            **values,
        })
        picking.action_confirm()
        picking.move_ids.quantity = 1
        picking.move_ids.picked = True
        return picking

    def _sms(self, picking):
        return self.env['sms.sms'].search([('mail_message_id', 'in', picking.message_ids.ids)])

    def test_companies_use_new_wording(self):
        self.assertEqual(self.company.stock_sms_confirmation_template_id, self.our_template)
        new_company = self.env['res.company'].create({'name': 'Another Shop'})
        self.assertEqual(new_company.stock_sms_confirmation_template_id, self.our_template)

    def test_shipped_text_is_queued_through_nestsms(self):
        picking = self._delivery()
        picking.carrier_tracking_ref = '747'
        picking.button_validate()
        self.assertEqual(picking.state, 'done')

        sms = self._sms(picking)
        self.assertEqual(len(sms), 1)
        self.assertEqual(sms.body, "Flagship-Store: Your order S00123 has been shipped. Tracking ref: 747.")
        self.assertTrue(is_gsm7(sms.body))
        self.assertEqual(sms.state, 'outgoing')
        self.assertFalse(self.nestsms.calls, "Queued, not sent inside the validation.")

        self._send_queue()
        self.assertEqual(self.nestsms.calls[0]['payload']['to'], '9841234567')

    def test_without_tracking_ref(self):
        picking = self._delivery()
        picking.button_validate()
        self.assertEqual(self._sms(picking).body, "Flagship-Store: Your order S00123 has been shipped.")

    def test_inventory_setting_off(self):
        self.company.stock_text_confirmation = False
        picking = self._delivery()
        picking.button_validate()
        self.assertFalse(self._sms(picking))

    def test_opted_out_customer(self):
        self.env['phone.blacklist'].sudo().add('+9779841234567')
        picking = self._delivery()
        picking.button_validate()
        self.assertEqual(picking.state, 'done')
        self.assertFalse(self._sms(picking))
