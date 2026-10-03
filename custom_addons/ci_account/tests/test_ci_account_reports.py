# -*- coding: utf-8 -*-
import io
import json
import zipfile

from odoo import Command, http
from odoo.tests import HttpCase, tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


class CiAccountReportCommon(AccountTestInvoicingCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.company_data['company']
        cls.revenue = cls.company_data['default_account_revenue']
        cls.expense = cls.company_data['default_account_expense']
        cls.receivable = cls.company_data['default_account_receivable']
        cls.payable = cls.company_data['default_account_payable']
        cls.tax_sale = cls.company_data['default_tax_sale']
        cls.no_tax = cls.env['account.tax']

        # 2024: profit of 600 (income 1000, expense 400), all unpaid
        cls.invoice_2024 = cls._create_invoice_one_line(
            price_unit=1000.0, tax_ids=cls.no_tax, invoice_date='2024-06-15', post=True)
        cls.bill_2024 = cls._create_invoice_one_line(
            move_type='in_invoice', price_unit=400.0, tax_ids=cls.no_tax, invoice_date='2024-07-01', post=True)
        # 2025: an invoice of 2000 + sale tax, due 30 days later, paid 500 on 2025-04-20
        cls.invoice_2025 = cls._create_invoice_one_line(
            price_unit=2000.0, tax_ids=cls.tax_sale, invoice_date='2025-03-10', post=True,
            invoice_payment_term_id=False, invoice_date_due='2025-04-09')
        cls.payment_2025 = cls._register_payment(cls.invoice_2025, payment_date='2025-04-20', amount=500.0)
        cls.tax_2025 = cls.invoice_2025.amount_tax

    def _report(self, model, **options):
        return self.env[model].get_report_information(options)

    def _lines(self, info):
        return {line['id']: line for line in info['lines']}

    def _value(self, line, index=0):
        return line['columns'][index]['no_format']

    def _custom(self, date_from, date_to):
        return {'filter': 'custom', 'date_from': date_from, 'date_to': date_to}


@tagged('post_install', '-at_install')
class TestCiAccountReports(CiAccountReportCommon):

    def test_balance_sheet_balances(self):
        info = self._report('ci.account.report.balance.sheet', date=self._custom('2025-01-01', '2025-12-31'))
        lines = self._lines(info)
        total_assets = self._value(lines['total-assets'])
        liabilities_equity = self._value(lines['node-liabilities_equity'])
        self.assertAlmostEqual(total_assets, liabilities_equity)
        # invoices 1000 + 2000 + tax, payment of 500 on the outstanding receipts account: all assets
        self.assertAlmostEqual(total_assets, 1000.0 + 2000.0 + self.tax_2025)
        self.assertAlmostEqual(self._value(lines['node-current_year_earnings']), 2000.0)
        self.assertAlmostEqual(self._value(lines['node-previous_years_earnings']), 600.0)

    def test_balance_sheet_account_lines_and_drilldown(self):
        options = {'date': self._custom('2025-01-01', '2025-12-31')}
        info = self._report('ci.account.report.balance.sheet', **options)
        lines = self._lines(info)
        receivable_line = lines[f'acc-{self.receivable.id}']
        self.assertEqual(receivable_line['parent_id'], 'node-asset_receivable')
        self.assertAlmostEqual(self._value(receivable_line), 1000.0 + 2000.0 + self.tax_2025 - 500.0)
        action = self.env['ci.account.report.balance.sheet'].action_open_line(
            info['options'], receivable_line['id'], 'journal_items')
        amls = self.env['account.move.line'].search(action['domain'])
        self.assertAlmostEqual(sum(amls.mapped('balance')), self._value(receivable_line))
        gl_action = self.env['ci.account.report.balance.sheet'].action_open_line(
            info['options'], receivable_line['id'], 'general_ledger')
        self.assertEqual(gl_action['context']['ci_report_options']['account_ids'], [self.receivable.id])

    def test_balance_sheet_comparison(self):
        info = self._report('ci.account.report.balance.sheet', date=self._custom('2025-01-01', '2025-12-31'),
                            comparison={'filter': 'same_last_year', 'number_period': 1})
        self.assertEqual(len(info['columns']), 3)  # 2025, 2024, growth %
        lines = self._lines(info)
        total_assets = lines['total-assets']
        self.assertAlmostEqual(self._value(total_assets, 1), 1000.0)
        expected_growth = (self._value(total_assets, 0) - 1000.0) / 1000.0 * 100.0
        self.assertAlmostEqual(self._value(total_assets, 2), expected_growth)

    def test_profit_and_loss(self):
        info = self._report('ci.account.report.profit.loss', date=self._custom('2025-01-01', '2025-12-31'))
        lines = self._lines(info)
        self.assertAlmostEqual(self._value(lines['node-revenue']), 2000.0)
        self.assertAlmostEqual(self._value(lines['node-net_profit']), 2000.0)
        info = self._report('ci.account.report.profit.loss', date=self._custom('2024-01-01', '2024-12-31'))
        lines = self._lines(info)
        self.assertAlmostEqual(self._value(lines['node-revenue']), 1000.0)
        self.assertAlmostEqual(self._value(lines['node-net_profit']), 600.0)

    def test_draft_entries_option(self):
        self._create_invoice_one_line(price_unit=300.0, tax_ids=self.no_tax, invoice_date='2025-05-01')
        date = self._custom('2025-01-01', '2025-12-31')
        posted = self._lines(self._report('ci.account.report.profit.loss', date=date))
        with_draft = self._lines(self._report('ci.account.report.profit.loss', date=date, all_entries=True))
        self.assertAlmostEqual(self._value(posted['node-revenue']), 2000.0)
        self.assertAlmostEqual(self._value(with_draft['node-revenue']), 2300.0)

    def test_trial_balance(self):
        info = self._report('ci.account.report.trial.balance', date=self._custom('2025-01-01', '2025-12-31'))
        lines = self._lines(info)
        total = self._value_list(lines['total-0'])
        self.assertAlmostEqual(total[0], total[1])  # initial debit = credit
        self.assertAlmostEqual(total[2], total[3])  # period debit = credit
        self.assertAlmostEqual(total[4], total[5])  # end debit = credit
        # the 2024 revenue is not carried forward on the income account...
        revenue = self._value_list(lines[f'acc-{self.revenue.id}'])
        self.assertEqual(revenue[:2], [0.0, 0.0])
        self.assertAlmostEqual(revenue[3], 2000.0)
        # ... but as undistributed earnings on the current year earnings account
        unaffected = self.env['ci.account.report']._ci_unaffected_earnings_account()
        if unaffected:
            self.assertAlmostEqual(self._value_list(lines[f'acc-{unaffected.id}'])[1], 600.0)
        else:
            self.assertAlmostEqual(self._value_list(lines['undistributed-0'])[1], 600.0)

    def _value_list(self, line):
        return [col['no_format'] for col in line['columns']]

    def test_trial_balance_hierarchy(self):
        group = self.env['account.group'].create({
            'name': 'Everything', 'code_prefix_start': '0', 'code_prefix_end': '9', 'company_id': self.company.id,
        })
        info = self._report('ci.account.report.trial.balance', date=self._custom('2025-01-01', '2025-12-31'),
                            hierarchy=True, unfold_all=True)
        lines = self._lines(info)
        group_line = lines[f'grp-{group.id}']
        self.assertTrue(group_line['unfoldable'])
        self.assertEqual(lines[f'acc-{self.revenue.id}']['parent_id'], group_line['id'])

    def test_general_ledger(self):
        report = self.env['ci.account.report.general.ledger']
        info = self._report('ci.account.report.general.ledger', date=self._custom('2025-01-01', '2025-12-31'))
        line_id = f'acc-{self.receivable.id}'
        account_line = self._lines(info)[line_id]
        self.assertTrue(account_line['lazy'])
        children = report.get_expanded_lines(info['options'], line_id)
        self.assertEqual(children[0]['id'], f'{line_id}|initial-0')
        self.assertAlmostEqual(self._value(children[0], 6), 1000.0)  # 2024 invoice
        aml_lines = [line for line in children if '|aml-' in line['id']]
        self.assertEqual(len(aml_lines), 2)  # 2025 invoice + payment
        self.assertAlmostEqual(self._value(aml_lines[-1], 6), 1000.0 + 2000.0 + self.tax_2025 - 500.0)
        self.assertTrue(children[-1]['id'].endswith('|total-0'))

    def test_general_ledger_load_more(self):
        report = self.env['ci.account.report.general.ledger']
        options = report._ci_get_options({'date': self._custom('2025-01-01', '2025-12-31')})
        line_id = f'acc-{self.receivable.id}'
        first = report._ci_expand_line(options, line_id, limit=1)
        load_more = first[-1]
        self.assertIn('load_more', load_more)
        rest = report.get_expanded_lines(options, line_id, load_more['load_more'])
        self.assertTrue(rest[-1]['id'].endswith('|total-0'))
        self.assertAlmostEqual(self._value(rest[-2], 6), 1000.0 + 2000.0 + self.tax_2025 - 500.0)

    def test_general_ledger_unfolded_lines_are_expanded(self):
        line_id = f'acc-{self.receivable.id}'
        info = self._report('ci.account.report.general.ledger', date=self._custom('2025-01-01', '2025-12-31'),
                            unfolded_lines=[line_id])
        self.assertTrue(any(line['parent_id'] == line_id for line in info['lines']))

    def test_partner_ledger(self):
        info = self._report('ci.account.report.partner.ledger', date=self._custom('2025-01-01', '2025-12-31'),
                            account_type='receivable')
        line = self._lines(info)[f'partner-{self.partner_a.id}']
        self.assertAlmostEqual(self._value(line, 5), 2000.0 + self.tax_2025)  # debit
        self.assertAlmostEqual(self._value(line, 6), 500.0)  # credit
        self.assertAlmostEqual(self._value(line, 7), 1000.0 + 2000.0 + self.tax_2025 - 500.0)  # balance

    def test_aged_receivable_buckets_and_past_date(self):
        info = self._report('ci.account.report.aged.receivable', date=self._custom('2025-05-15', '2025-05-15'))
        line = self._lines(info)[f'partner-{self.partner_a.id}']
        values = [col['no_format'] for col in line['columns']]
        # 2025 invoice due 2025-04-09: 36 days late -> 31-60; 2024 invoice: older
        self.assertAlmostEqual(values[4], 2000.0 + self.tax_2025 - 500.0)
        self.assertAlmostEqual(values[7], 1000.0)
        # as of a date before the payment, the full invoice is still open
        info = self._report('ci.account.report.aged.receivable', date=self._custom('2025-04-15', '2025-04-15'))
        line = self._lines(info)[f'partner-{self.partner_a.id}']
        self.assertAlmostEqual(line['columns'][3]['no_format'], 2000.0 + self.tax_2025)  # 1-30
        self.assertAlmostEqual(line['columns'][8]['no_format'], 3000.0 + self.tax_2025)

    def test_aged_payable(self):
        info = self._report('ci.account.report.aged.payable', date=self._custom('2025-01-31', '2025-01-31'))
        line = self._lines(info)[f'partner-{self.partner_a.id}']
        self.assertAlmostEqual(line['columns'][8]['no_format'], 400.0)
        children = self.env['ci.account.report.aged.payable'].get_expanded_lines(info['options'], line['id'])
        self.assertEqual(len(children), 1)

    def test_tax_report(self):
        info = self._report('ci.account.report.tax', date=self._custom('2025-03-01', '2025-03-31'))
        lines = self._lines(info)
        tax_line = lines[f'tax-{self.tax_sale.id}']
        self.assertAlmostEqual(self._value(tax_line, 0), 2000.0)
        self.assertAlmostEqual(self._value(tax_line, 1), self.tax_2025)
        self.assertAlmostEqual(self._value(lines['total-0'], 1), self.tax_2025)
        domain = self.env['ci.account.report.tax'].action_open_line(info['options'], tax_line['id'])['domain']
        self.assertTrue(self.env['account.move.line'].search(domain))

    def test_cash_flow(self):
        statement_line = self.env['account.bank.statement.line'].create({
            'journal_id': self.company_data['default_journal_bank'].id,
            'date': '2025-04-25',
            'payment_ref': 'customer payment',
            'partner_id': self.partner_a.id,
            'amount': 500.0,
        })
        # match the bank line with the payment through the outstanding receipts account
        _liquidity, suspense, _other = statement_line._seek_for_lines()
        payment_line = self.payment_2025.move_id.line_ids.filtered(
            lambda l: l.account_id == self.payment_2025.outstanding_account_id)
        suspense.with_context(skip_account_move_synchronization=True).account_id = payment_line.account_id
        (suspense + payment_line).reconcile()

        info = self._report('ci.account.report.cash.flow', date=self._custom('2025-01-01', '2025-12-31'),
                            unfold_all=True)
        lines = self._lines(info)
        self.assertAlmostEqual(self._value(lines['node-net']), 500.0)
        self.assertAlmostEqual(self._value(lines['activity-operating']), 500.0)
        self.assertAlmostEqual(self._value(lines[f'activity-operating|dir-in|acc-{self.receivable.id}']), 500.0)
        self.assertAlmostEqual(self._value(lines['node-closing']) - self._value(lines['node-opening']), 500.0)

    def test_journal_report(self):
        report = self.env['ci.account.report.journal']
        info = self._report('ci.account.report.journal', date=self._custom('2025-03-01', '2025-03-31'))
        journal = self.invoice_2025.journal_id
        line = self._lines(info)[f'journal-{journal.id}']
        self.assertAlmostEqual(self._value(line, 3), self._value(line, 4))
        children = report.get_expanded_lines(info['options'], line['id'])
        self.assertIn(f'journal-{journal.id}|move-{self.invoice_2025.id}', [child['id'] for child in children])

    def test_journal_filter(self):
        sale_journal = self.invoice_2025.journal_id
        info = self._report('ci.account.report.profit.loss', date=self._custom('2025-01-01', '2025-12-31'))
        journals = info['options']['journals']
        for journal in journals:
            journal['selected'] = journal['id'] == self.company_data['default_journal_purchase'].id
        info = self._report('ci.account.report.profit.loss', date=self._custom('2025-01-01', '2025-12-31'),
                            journals=journals)
        self.assertAlmostEqual(self._value(self._lines(info)['node-revenue']), 0.0)
        self.assertNotIn(sale_journal.id, [j['id'] for j in info['options']['journals'] if j['selected']])

    def test_hide_zero_lines(self):
        unused = self.env['account.account'].create({
            'code': '480099', 'name': 'Unused income', 'account_type': 'income',
        })
        self.env['account.move'].create({
            'journal_id': self.company_data['default_journal_misc'].id,
            'date': '2025-02-01',
            'line_ids': [
                Command.create({'account_id': unused.id, 'balance': 100.0}),
                Command.create({'account_id': unused.id, 'balance': -100.0}),
            ],
        }).action_post()
        date = self._custom('2025-01-01', '2025-12-31')
        hidden = self._lines(self._report('ci.account.report.profit.loss', date=date))
        shown = self._lines(self._report('ci.account.report.profit.loss', date=date, hide_zero=False))
        self.assertNotIn(f'acc-{unused.id}', hidden)
        self.assertIn(f'acc-{unused.id}', shown)

    def test_exports(self):
        options = {'date': self._custom('2025-01-01', '2025-12-31')}
        for model in ('ci.account.report.balance.sheet', 'ci.account.report.general.ledger',
                      'ci.account.report.aged.receivable', 'ci.account.report.tax'):
            content, filename = self.env[model].export_to_xlsx(options)
            self.assertTrue(filename.endswith('.xlsx'))
            self.assertTrue(zipfile.is_zipfile(io.BytesIO(content)))
        html = self.env['ir.actions.report']._render_qweb_html(
            'ci_account.action_ci_report_pdf', None, data={'ci_report': {
                'title': 'Balance Sheet', 'company_name': self.company.name, 'filters': '',
                'column_groups': [], 'columns': [{'name': 'Balance', 'figure': 'monetary'}],
                'lines': self.env['ci.account.report.balance.sheet']._ci_export_data(options)[1],
            }})[0]
        self.assertIn(b'Total ASSETS', html)
        # in test mode the PDF engine falls back to the HTML rendering
        content, filename = self.env['ci.account.report.trial.balance'].export_to_pdf(options)
        self.assertTrue(filename.endswith('.pdf'))
        self.assertIn(b'Trial Balance', content)

    def test_reports_need_accounting_access(self):
        user = self.env['res.users'].create({
            'name': 'Billing only', 'login': 'billing_only',
            'group_ids': [Command.set([self.env.ref('account.group_account_invoice').id])],
            'company_id': self.company.id, 'company_ids': [Command.set(self.company.ids)],
        })
        with self.assertRaises(Exception):
            self.env['ci.account.report.balance.sheet'].with_user(user).get_report_information({})
        auditor = self.env['res.users'].create({
            'name': 'Auditor', 'login': 'ci_auditor',
            'group_ids': [Command.set([self.env.ref('account.group_account_readonly').id])],
            'company_id': self.company.id, 'company_ids': [Command.set(self.company.ids)],
        })
        info = self.env['ci.account.report.balance.sheet'].with_user(auditor).get_report_information(
            {'date': self._custom('2025-01-01', '2025-12-31')})
        self.assertTrue(info['lines'])


@tagged('post_install', '-at_install')
class TestCiAccountReportHttp(HttpCase, CiAccountReportCommon):

    def test_export_controller(self):
        self.authenticate(self.env.user.login, self.env.user.login)
        response = self.url_open('/ci_account/report/export', data={
            'report_model': 'ci.account.report.trial.balance',
            'options': json.dumps({'date': self._custom('2025-01-01', '2025-12-31')}),
            'file_type': 'xlsx',
            'context': json.dumps({'allowed_company_ids': self.company.ids}),
            'csrf_token': http.Request.csrf_token(self),
        })
        self.assertEqual(response.status_code, 200)
        self.assertTrue(zipfile.is_zipfile(io.BytesIO(response.content)))

    def test_export_controller_refuses_other_models(self):
        self.authenticate(self.env.user.login, self.env.user.login)
        response = self.url_open('/ci_account/report/export', data={
            'report_model': 'res.users',
            'options': '{}',
            'file_type': 'xlsx',
            'csrf_token': http.Request.csrf_token(self),
        })
        self.assertEqual(response.status_code, 400)

    def test_report_client_action_tour(self):
        self.start_tour('/odoo/balance-sheet', 'ci_account_report_tour', login=self.env.user.login)
