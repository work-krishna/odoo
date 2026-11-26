# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo.tests import tagged

from odoo.addons.delivery_ncm.tests.common import NcmCommon
from odoo.addons.sms_nestsms.tests.common import patch_nestsms
from odoo.addons.sms_nestsms.tools.sms_api import is_gsm7


@tagged('post_install', '-at_install')
class TestNcmDeliverySms(NcmCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.company.write({'sms_nestsms_api_key': 'nsms_live_test', 'sms_brand_name': 'Flagship-Store'})
        cls.ncm.ncm_notify_customer_sms = True

    def setUp(self):
        super().setUp()
        self.nestsms = patch_nestsms(self)
        self.order = self._confirmed_order()
        self.picking = self.order.picking_ids
        self._route_created_order()
        self._validate(self.picking.with_context(skip_sms=True))
        self.assertTrue(self.picking.ncm_order_id)

    def _sms(self):
        return self.env['sms.sms'].search([('mail_message_id', 'in', self.picking.message_ids.ids)], order='id')

    def test_out_for_delivery_then_delivered(self):
        self.picking._ncm_set_current_status('Sent for Delivery')
        sms = self._sms()
        self.assertEqual(len(sms), 1)
        self.assertEqual(sms.number, '+9779841234567')
        self.assertTrue(self.picking.ncm_cod_amount, "Unpaid order: NCM collects cash.")
        self.assertEqual(sms.body, (
            f"Flagship-Store: Your order {self.order.name} is out for delivery with Nepal Can Move today. "
            f"Please keep Rs. {self.picking.ncm_cod_amount:.2f} ready."
        ))

        self.picking._ncm_set_current_status('Delivered')
        sms = self._sms()
        self.assertEqual(len(sms), 2)
        self.assertEqual(sms[1].body, f"Flagship-Store: Your order {self.order.name} has been delivered. Thank you for shopping with us!")

        self.assertTrue(all(is_gsm7(body) for body in sms.mapped('body')))
        sms.send(unlink_sent=False)  # only the parcel's texts: the order confirmation is queued too
        self.assertEqual([call['payload']['to'] for call in self.nestsms.calls], ['9841234567', '9841234567'])
        self.assertEqual(set(sms.mapped('state')), {'pending'})

    def test_prepaid_parcel_no_cash_line(self):
        self.picking.ncm_cod_amount = 0.0
        self.picking._ncm_set_current_status('Sent for Delivery')
        self.assertNotIn('Rs.', self._sms().body)

    def test_once_per_stage(self):
        """A failed attempt and a second run out for delivery text the customer only once."""
        self.picking._ncm_set_current_status('Sent for Delivery')
        self.picking._ncm_set_current_status('Arrived')
        self.picking._ncm_set_current_status('Sent for Delivery')
        self.picking._ncm_set_current_status('Sent for Delivery')
        self.assertEqual(len(self._sms()), 1)
        self.assertEqual(self.picking.ncm_sms_sent_states, 'out_for_delivery')

    def test_other_stages_silent(self):
        self.picking._ncm_set_current_status('Pickup Complete')
        self.picking._ncm_set_current_status('In Transit')
        self.assertFalse(self._sms())

    def test_carrier_setting_off(self):
        self.ncm.ncm_notify_customer_sms = False
        self.picking._ncm_set_current_status('Sent for Delivery')
        self.assertFalse(self._sms())
