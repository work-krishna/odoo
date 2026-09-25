# -*- coding: utf-8 -*-
from datetime import date, timedelta
from unittest.mock import patch

import requests

from odoo import Command, fields
from odoo.exceptions import UserError
from odoo.tests import new_test_user, tagged

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
        cls.journal = cls.company_data['default_journal_sale']
        cls.code = cls.journal.code

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

    # ------------------------------------------------------------------
    # Numbering next to legacy (Gregorian) names
    # ------------------------------------------------------------------

    def _legacy_invoices(self, *invoice_dates):
        """Invoices posted before IRD numbering was switched on."""
        self.company.l10n_np_bs_invoice_numbering = False
        invoices = self.env['account.move']
        for invoice_date in invoice_dates:
            invoices |= self._invoice(invoice_date)
        self.company.l10n_np_bs_invoice_numbering = True
        return invoices

    def test_numbering_after_gregorian_year_range_names(self):
        # Odoo's fiscal year ends on July 16, so the journal already holds INV/26-27/ names.
        self.company.write({'fiscalyear_last_month': '7', 'fiscalyear_last_day': 16})
        legacy = self._legacy_invoices('2026-07-20')
        self.assertEqual(legacy.name, f'{self.code}/26-27/0001')
        first = self._invoice('2026-08-01')
        second = self._invoice('2026-08-02')
        self.assertEqual(first.name, f'{self.code}/2083-84/0001')
        self.assertEqual(second.name, f'{self.code}/2083-84/0002')
        # The legacy invoice keeps its name and can still be corrected.
        legacy.button_draft()
        legacy.action_post()
        self.assertEqual(legacy.name, f'{self.code}/26-27/0001')

    def test_late_invoice_after_mid_year_switch(self):
        legacy = self._legacy_invoices('2026-07-05')
        current = self._invoice('2026-09-20')
        late = self._invoice('2026-07-10')  # still FY 2082/83
        self.assertEqual(legacy.name, f'{self.code}/2026/00001')
        self.assertEqual(current.name, f'{self.code}/2083-84/0001')
        self.assertEqual(late.name, f'{self.code}/2082-83/0001')

    def test_legacy_invoice_inside_its_chain_cannot_be_deleted(self):
        legacy = self._legacy_invoices('2026-07-01', '2026-07-02', '2026-07-03')
        billing = new_test_user(
            self.env, login='np_billing', groups='base.group_user,account.group_account_invoice',
            company_id=self.company.id, company_ids=[Command.set(self.company.ids)],
        )
        middle = legacy[1].with_user(billing)
        middle.button_draft()
        with self.assertRaises(UserError):
            middle.unlink()

    def test_receipts_and_entries_keep_out_of_the_ird_series(self):
        with patch(POST, return_value=FakeResponse('200')):
            invoice = self._invoice('2026-09-23')
            receipt = self._create_invoice(
                move_type='out_receipt', invoice_date='2026-09-24', date='2026-09-24', post=True,
                partner_id=self.partner_a,
                invoice_line_ids=[Command.create({'name': 'Cover', 'quantity': 1, 'price_unit': 100.0, 'tax_ids': [Command.set([])]})],
            )
            entry = self.env['account.move'].create({
                'move_type': 'entry', 'journal_id': self.journal.id, 'date': '2026-09-24',
                'line_ids': [
                    Command.create({'name': 'Adjustment', 'account_id': self.company_data['default_account_revenue'].id, 'debit': 10.0}),
                    Command.create({'name': 'Adjustment', 'account_id': self.company_data['default_account_expense'].id, 'credit': 10.0}),
                ],
            })
            entry.action_post()
            next_invoice = self._invoice('2026-09-25')
        self.assertEqual(invoice.name, f'{self.code}/2083-84/0001')
        self.assertEqual(next_invoice.name, f'{self.code}/2083-84/0002')
        self.assertEqual(receipt.name, f'{self.code}/RCPT/2083-84/0001')
        self.assertEqual(entry.name, f'{self.code}/MISC/2083-84/0001')
        self.assertFalse(receipt.l10n_np_cbms_state)

    def test_resequence_is_blocked_for_bs_numbered_journals(self):
        invoices = self._invoice('2026-12-20') | self._invoice('2027-01-05') | self._invoice('2027-01-06')
        wizard_model = self.env['account.resequence.wizard']
        first_name = f'{self.code}/2083-84/0001'
        with self.assertRaises(UserError):
            wizard_model.with_context(active_model='account.move', active_ids=invoices.ids).create({'first_name': first_name})
        wizard = wizard_model.create({'move_ids': [Command.set(invoices.ids)], 'first_name': first_name})
        with self.assertRaises(UserError):
            wizard.resequence()
        self.assertEqual(invoices.mapped('name'), [f'{self.code}/2083-84/000{n}' for n in (1, 2, 3)])

    def test_numbering_supported_range(self):
        last_supported = self._invoice('2043-07-16')  # last day of FY 2099/00
        self.assertEqual(last_supported.name, f'{self.code}/2099-00/0001')
        with self.assertRaisesRegex(UserError, 'fiscal year 2099/00'):
            self._invoice('2043-08-01')  # FY 2100/01
        with self.assertRaisesRegex(UserError, 'fiscal year 2099/00'):
            self._invoice('2050-01-01')  # after the BS calendar table

    def test_locked_fiscal_year_does_not_renumber_invoice(self):
        # FY 2082/83 is locked: the accounting date would move to FY 2083/84.
        self.company.sale_lock_date = date(2026, 7, 16)
        late = self._invoice('2026-07-10', post=False)
        with self.assertRaisesRegex(UserError, 'fiscal year 2083/84'):
            late.action_post()

    def test_lock_date_within_fiscal_year(self):
        # A lock inside the fiscal year only moves the accounting date within it.
        self.company.sale_lock_date = date(2026, 8, 16)
        invoice = self._invoice('2026-08-10')
        self.assertGreater(invoice.date, date(2026, 8, 16))
        self.assertEqual(invoice.name, f'{self.code}/2083-84/0001')
        self.assertEqual(invoice.l10n_np_fiscal_year, '2083/84')

    # ------------------------------------------------------------------
    # CBMS: invoices IRD holds or may hold
    # ------------------------------------------------------------------

    def test_reported_invoice_cannot_be_renamed(self):
        with patch(POST, return_value=FakeResponse('200')):
            invoice = self._invoice('2026-09-23')
            invoice._l10n_np_cbms_send()
        with self.assertRaises(UserError):
            invoice.name = f'{self.code}/2083-84/0005'
        with self.assertRaises(UserError):
            invoice.name = False
        # Core only guards the other bill fields of posted moves outside this context.
        with self.assertRaises(UserError):
            invoice.with_context(skip_readonly_check=True).write({'invoice_date': '2026-09-24'})

    def test_reported_invoice_cannot_be_resequenced(self):
        # The resequence wizard of a Gregorian-numbered journal renames through write.
        self.company.l10n_np_bs_invoice_numbering = False
        with patch(POST, return_value=FakeResponse('200')):
            reported = self._invoice('2026-09-24') | self._invoice('2026-09-25')
            reported._l10n_np_cbms_send()
        wizard = self.env['account.resequence.wizard'].with_context(
            active_model='account.move', active_ids=reported.ids,
        ).create({'first_name': f'{self.code}/2026/00005'})
        with self.assertRaises(UserError):
            wizard.resequence()
        self.assertEqual(reported.mapped('name'), [f'{self.code}/2026/00001', f'{self.code}/2026/00002'])

    def test_uncertain_send_locks_the_invoice(self):
        with patch(POST, side_effect=requests.ReadTimeout('read timed out')):
            invoice = self._invoice('2026-09-23')
            invoice._l10n_np_cbms_send()
        self.assertEqual(invoice.l10n_np_cbms_state, 'error')
        # IRD may hold the bill: no reset, no cancel, the name stays.
        with self.assertRaises(UserError):
            invoice.button_draft()
        with self.assertRaises(UserError):
            invoice.button_cancel()
        with self.assertRaises(UserError):
            invoice.name = False
        with patch(POST, return_value=FakeResponse('101')):  # IRD did keep it
            invoice._l10n_np_cbms_send()
        self.assertEqual(invoice.l10n_np_cbms_state, 'sent')

    def test_interrupted_send_locks_the_invoice(self):
        # The process dies once the request is out: the attempt recorded (and committed,
        # see test_cron_commits_after_each_invoice) beforehand survives.
        invoice = self._invoice('2026-09-23')
        with patch(POST, side_effect=RuntimeError('worker killed')):
            try:
                invoice._l10n_np_cbms_send()
            except RuntimeError:
                pass
        self.assertEqual(invoice.l10n_np_cbms_attempts, 1)
        with self.assertRaises(UserError):
            invoice.button_draft()
        with patch(POST, return_value=FakeResponse('101')):
            invoice._l10n_np_cbms_send()
        self.assertEqual(invoice.l10n_np_cbms_state, 'sent')

    def test_cbms_101_for_another_bill_is_an_error(self):
        # IRD holds a bill with this number that this database has no record of sending.
        with patch(POST, return_value=FakeResponse('101')):
            unknown = self._invoice('2026-09-23')
            unknown._l10n_np_cbms_send()
        self.assertEqual(unknown.l10n_np_cbms_state, 'error')
        with self.assertRaises(UserError):
            unknown.button_draft()
        # IRD may hold the first version; the buyer PAN changed since.
        with patch(POST, side_effect=requests.ReadTimeout('read timed out')):
            changed = self._invoice('2026-09-23')
            changed._l10n_np_cbms_send()
        self.partner_a.vat = '300000099'
        with patch(POST, return_value=FakeResponse('101')):
            changed._l10n_np_cbms_send()
        self.assertEqual(changed.l10n_np_cbms_state, 'error')
        self.assertIn('differ', changed.l10n_np_cbms_response)

    def test_rejected_invoice_stays_correctable(self):
        with patch(POST, return_value=FakeResponse('102')):
            invoice = self._invoice('2026-09-23')
            invoice._l10n_np_cbms_send()
            self.assertEqual(invoice.l10n_np_cbms_state, 'error')
            invoice.button_draft()  # IRD did not store it
            self.assertFalse(invoice.l10n_np_cbms_state)
            invoice.action_post()
            self.assertEqual(invoice.l10n_np_cbms_state, 'to_send')
            invoice._l10n_np_cbms_send()
            invoice.button_cancel()
        self.assertEqual(invoice.state, 'cancel')
        self.assertFalse(invoice.l10n_np_cbms_state)

    def test_http_status_tells_whether_ird_may_hold_the_bill(self):
        with patch(POST, return_value=FakeResponse('<html>Not Found</html>', 404)):
            refused = self._invoice('2026-09-23')
            refused._l10n_np_cbms_send()
        refused.button_draft()  # the request was refused
        with patch(POST, return_value=FakeResponse('<html>Bad Gateway</html>', 502)):
            unknown = self._invoice('2026-09-23')
            unknown._l10n_np_cbms_send()
        self.assertEqual(unknown.l10n_np_cbms_state, 'error')
        with self.assertRaises(UserError):
            unknown.button_draft()

    # ------------------------------------------------------------------
    # CBMS: cron, amounts, real time
    # ------------------------------------------------------------------

    def test_cron_only_picks_cbms_enabled_invoices(self):
        queued = self._invoice('2026-09-23') | self._invoice('2026-09-24')
        self.company.l10n_np_cbms_enabled = False
        picked = []
        self.patch(type(self.env['account.move']), '_l10n_np_cbms_send', lambda moves: picked.extend(moves.ids))
        self.env['account.move']._cron_l10n_np_cbms_sync()
        self.assertEqual(queued.mapped('l10n_np_cbms_state'), ['to_send', 'to_send'])
        self.assertFalse(set(picked) & set(queued.ids))

    def test_cron_commits_after_each_invoice(self):
        invoices = self._invoice('2026-09-23') | self._invoice('2026-09-24')
        commits = []

        def commit_progress(cron, processed=0, remaining=None, **kwargs):
            commits.append((processed, invoices.mapped('l10n_np_cbms_state'), invoices.mapped('l10n_np_cbms_attempts')))
            return 60.0

        self.patch(type(self.env['account.move']), '_can_commit', staticmethod(lambda: True))
        self.patch(self.registry['ir.cron'], '_commit_progress', commit_progress)
        with patch(POST, return_value=FakeResponse('200')) as post:
            self.env['account.move']._cron_l10n_np_cbms_sync()
        # The attempt is committed before the request, the outcome right after it.
        self.assertIn((0, ['to_send', 'to_send'], [1, 0]), commits)
        self.assertIn((1, ['sent', 'to_send'], [1, 0]), commits)
        self.assertIn((1, ['sent', 'sent'], [1, 1]), commits)
        self.assertLessEqual(post.call_args.kwargs['timeout'], 10)

    def test_cbms_buckets_include_cash_rounding(self):
        rounding = self.env['account.cash.rounding'].create({
            'name': '1 NPR', 'rounding': 1.0, 'strategy': 'add_invoice_line', 'rounding_method': 'HALF-UP',
            'profit_account_id': self.company_data['default_account_revenue'].id,
            'loss_account_id': self.company_data['default_account_expense'].id,
        })
        invoice = self._create_invoice(
            invoice_date='2026-09-23', post=True, partner_id=self.partner_a, invoice_cash_rounding_id=rounding.id,
            invoice_line_ids=[Command.create({
                'name': 'Phone', 'quantity': 1, 'price_unit': 999.55, 'tax_ids': [Command.set(self.vat13.ids)],
            })],
        )
        amounts = invoice._l10n_np_cbms_amounts()
        self.assertEqual(amounts['total_sales'], 1129.0)
        self.assertEqual(amounts['vat'], 129.94)
        self.assertAlmostEqual(
            amounts['taxable_sales_vat'] + amounts['vat'] + amounts['tax_exempted_sales'] + amounts['export_sales'],
            amounts['total_sales'],
        )

    def test_cbms_realtime_counts_from_posting(self):
        invoice = self._invoice('2026-09-23', post=False)
        # Drafted three days before it is confirmed.
        self.env.cr.execute("UPDATE account_move SET create_date = create_date - interval '3 days' WHERE id = %s", [invoice.id])
        invoice.invalidate_recordset(['create_date'])
        invoice.action_post()
        with patch(POST, return_value=FakeResponse('200')) as post:
            invoice._l10n_np_cbms_send()
        self.assertIs(post.call_args.kwargs['json']['isrealtime'], True)
        self.assertTrue(invoice.l10n_np_cbms_realtime)
        # Sent more than a day after posting: not real time.
        with patch(POST, return_value=FakeResponse('200')) as post:
            late = self._invoice('2026-09-23')
            late.l10n_np_cbms_posted_date = fields.Datetime.now() - timedelta(hours=25)
            late._l10n_np_cbms_send()
        self.assertIs(post.call_args.kwargs['json']['isrealtime'], False)
