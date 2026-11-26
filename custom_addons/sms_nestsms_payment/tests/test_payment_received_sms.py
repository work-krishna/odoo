# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.addons.sms_nestsms.tests.common import patch_nestsms, send_sms_queue
from odoo.addons.sms_nestsms.tools.sms_api import is_gsm7


@tagged('post_install', '-at_install')
class TestPaymentReceivedSms(AccountTestInvoicingCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.company.write({'sms_nestsms_api_key': 'nsms_live_test', 'sms_brand_name': 'Flagship-Store'})
        cls.customer = cls.env['res.partner'].create({
            'name': 'Sita Gurung',
            'phone': '+977 984-1234567',
            'country_id': cls.env.ref('base.np').id,
        })

    def setUp(self):
        super().setUp()
        self.nestsms = patch_nestsms(self)

    def _payment(self, **values):
        return self.env['account.payment'].create({
            'payment_type': 'inbound',
            'partner_type': 'customer',
            'partner_id': self.customer.id,
            'amount': 12345.0,
            'journal_id': self.company_data['default_journal_bank'].id,
            'memo': 'S00123',
            **values,
        })

    def _sms(self, payment):
        return self.env['sms.sms'].search([('mail_message_id', 'in', payment.message_ids.ids)])

    def test_payment_texts_customer(self):
        payment = self._payment()
        payment.action_post()

        sms = self._sms(payment)
        self.assertEqual(len(sms), 1)
        self.assertEqual(sms.body, "Flagship-Store: We have received your payment of Rs. 12345.00 for S00123. Thank you!")
        self.assertTrue(is_gsm7(sms.body))
        self.assertTrue(payment.sms_receipt_sent)
        send_sms_queue(self.env)
        self.assertEqual(self.nestsms.calls[0]['payload']['to'], '9841234567')

    def test_registered_invoice_payment(self):
        invoice = self.init_invoice('out_invoice', partner=self.customer, amounts=[500.0], post=True)
        payment = self.env['account.payment.register'].with_context(
            active_model='account.move', active_ids=invoice.ids,
        ).create({})._create_payments()
        self.assertEqual(len(self._sms(payment)), 1)
        self.assertIn(invoice.name, self._sms(payment).body)

    def test_once_per_payment(self):
        payment = self._payment()
        payment.action_post()
        payment.action_draft()
        payment.action_post()
        self.assertEqual(len(self._sms(payment)), 1)

    def test_vendor_payment_no_sms(self):
        payment = self._payment(payment_type='outbound', partner_type='supplier')
        payment.action_post()
        self.assertFalse(self._sms(payment))

    def test_setting_off(self):
        self.env.company.sms_notify_payment_received = False
        payment = self._payment()
        payment.action_post()
        self.assertFalse(self._sms(payment))
