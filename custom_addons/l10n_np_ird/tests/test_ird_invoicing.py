# -*- coding: utf-8 -*-
from unittest.mock import patch

import requests

from odoo import Command
from odoo.exceptions import UserError
from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon

POST = 'odoo.addons.l10n_np_ird.models.account_move.requests.post'


class FakeResponse:
    def __init__(self, text, status_code=200):
        self.text = text
        self.status_code = status_code


@tagged('post_install_l10n', 'post_install', '-at_install')
class TestIrdInvoicing(AccountTestInvoicingCommon):

    @classmethod
    @AccountTestInvoicingCommon.setup_country('np')
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.company_data['company']
        cls.company.write({
            'vat': '600000001',
            'l10n_np_cbms_enabled': True,
            'l10n_np_cbms_url': 'https://cbms.test',
            'l10n_np_cbms_username': 'tester',
            'l10n_np_cbms_password': 'secret',
        })
        chart = cls.env['account.chart.template'].with_company(cls.company)
        cls.vat13 = chart.ref('vat_sale_13')
        cls.vat0 = chart.ref('vat_sale_0')
        cls.partner_a.write({'vat': '300000002', 'country_id': cls.env.ref('base.np').id})

    def _invoice(self, invoice_date, taxes=None, move_type='out_invoice', amount=1000.0, post=True, partner=None):
        return self._create_invoice(
            move_type=move_type, invoice_date=invoice_date, post=post, partner_id=partner or self.partner_a,
            invoice_line_ids=[Command.create({
                'name': 'Phone', 'quantity': 1, 'price_unit': amount,
                'tax_ids': [Command.set((taxes or self.vat13).ids)],
            })],
        )

    # ------------------------------------------------------------------
    # Numbering
    # ------------------------------------------------------------------

    def test_numbering_enabled_by_chart(self):
        self.assertTrue(self.company.l10n_np_bs_invoice_numbering)

    def test_fiscal_year_numbering_resets_on_shrawan_1(self):
        with patch(POST, return_value=FakeResponse('200')):
            last_day_fy82 = self._invoice('2026-07-16')
            first_day_fy83 = self._invoice('2026-07-17')
            second_fy83 = self._invoice('2026-09-23')
        journal_code = first_day_fy83.journal_id.code
        self.assertEqual(last_day_fy82.name, f'{journal_code}/2082-83/0001')
        self.assertEqual(first_day_fy83.name, f'{journal_code}/2083-84/0001')
        self.assertEqual(second_fy83.name, f'{journal_code}/2083-84/0002')
        self.assertEqual(second_fy83.l10n_np_date_bs, '2083.06.07')
        self.assertEqual(second_fy83.l10n_np_fiscal_year, '2083/84')

    def test_credit_note_numbering(self):
        with patch(POST, return_value=FakeResponse('200')):
            refund = self._invoice('2026-09-23', move_type='out_refund')
        self.assertIn('/2083-84/0001', refund.name)

    # ------------------------------------------------------------------
    # CBMS
    # ------------------------------------------------------------------

    def test_cbms_invoice_payload_and_success(self):
        with patch(POST, return_value=FakeResponse('200')) as post:
            invoice = self._invoice('2026-09-23')
            self.assertEqual(invoice.l10n_np_cbms_state, 'to_send')
            self.env['account.move']._cron_l10n_np_cbms_sync()
        self.assertEqual(invoice.l10n_np_cbms_state, 'sent')
        self.assertTrue(invoice.l10n_np_cbms_realtime)
        url, = post.call_args.args
        payload = post.call_args.kwargs['json']
        self.assertEqual(url, 'https://cbms.test/api/bill')
        self.assertEqual(payload['seller_pan'], '600000001')
        self.assertEqual(payload['buyer_pan'], '300000002')
        self.assertEqual(payload['fiscal_year'], '2083.084')
        self.assertEqual(payload['invoice_number'], invoice.name)
        self.assertEqual(payload['invoice_date'], '2083.06.07')
        self.assertEqual(payload['taxable_sales_vat'], 1000.0)
        self.assertEqual(payload['vat'], 130.0)
        self.assertEqual(payload['total_sales'], 1130.0)
        self.assertEqual(payload['tax_exempted_sales'], 0.0)
        self.assertEqual(payload['username'], 'tester')

    def test_cbms_exempt_and_export_buckets(self):
        with patch(POST, return_value=FakeResponse('200')) as post:
            self._invoice('2026-09-23', taxes=self.vat0)._l10n_np_cbms_send()
            exempt = post.call_args.kwargs['json']
            foreign_buyer = self.env['res.partner'].create({'name': 'Delhi Buyer', 'country_id': self.env.ref('base.in').id})
            self._invoice('2026-09-23', taxes=self.vat0, partner=foreign_buyer)._l10n_np_cbms_send()
            export = post.call_args.kwargs['json']
        self.assertEqual((exempt['tax_exempted_sales'], exempt['export_sales'], exempt['vat']), (1000.0, 0.0, 0.0))
        self.assertEqual((export['tax_exempted_sales'], export['export_sales']), (0.0, 1000.0))

    def test_cbms_credit_note_uses_billreturn(self):
        with patch(POST, return_value=FakeResponse('200')) as post:
            invoice = self._invoice('2026-09-23')
            invoice._l10n_np_cbms_send()
            refund = invoice._reverse_moves([{'ref': 'Damaged phone returned', 'invoice_date': '2026-09-24'}])
            refund.action_post()
            refund._l10n_np_cbms_send()
        url, = post.call_args.args
        payload = post.call_args.kwargs['json']
        self.assertEqual(url, 'https://cbms.test/api/billreturn')
        self.assertEqual(payload['ref_invoice_number'], invoice.name)
        self.assertEqual(payload['credit_note_number'], refund.name)
        self.assertEqual(payload['credit_note_date'], '2083.06.08')
        self.assertEqual(payload['reason_for_return'], 'Damaged phone returned')
        self.assertEqual(payload['total_sales'], 1130.0)
        self.assertEqual(refund.l10n_np_cbms_state, 'sent')

    def test_cbms_errors_are_recorded_and_retried(self):
        with patch(POST, return_value=FakeResponse('100')):
            invoice = self._invoice('2026-09-23')
            invoice._l10n_np_cbms_send()
        self.assertEqual(invoice.l10n_np_cbms_state, 'error')
        self.assertIn('credentials', invoice.l10n_np_cbms_response)
        with patch(POST, side_effect=requests.ConnectionError('offline')):
            invoice.action_l10n_np_cbms_send()
        self.assertEqual(invoice.l10n_np_cbms_state, 'error')
        self.assertEqual(invoice.l10n_np_cbms_attempts, 2)
        with patch(POST, return_value=FakeResponse('101')):  # IRD already has it
            self.env['account.move']._cron_l10n_np_cbms_sync()
        self.assertEqual(invoice.l10n_np_cbms_state, 'sent')

    def test_reported_invoice_cannot_be_reset_to_draft(self):
        with patch(POST, return_value=FakeResponse('200')):
            invoice = self._invoice('2026-09-23')
            invoice._l10n_np_cbms_send()
        with self.assertRaises(UserError):
            invoice.button_draft()

    def test_vendor_bills_are_not_sent(self):
        with patch(POST, return_value=FakeResponse('200')) as post:
            bill = self._create_invoice(
                move_type='in_invoice', invoice_date='2026-09-23', post=True, partner_id=self.partner_a,
                invoice_line_ids=[Command.create({'name': 'Stock', 'quantity': 1, 'price_unit': 100.0})],
            )
            self.env['account.move']._cron_l10n_np_cbms_sync()
        self.assertFalse(bill.l10n_np_cbms_state)
        post.assert_not_called()
