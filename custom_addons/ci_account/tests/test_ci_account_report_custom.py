# -*- coding: utf-8 -*-
from odoo import Command
from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged('post_install', '-at_install')
class TestCiAccountReportCustom(AccountTestInvoicingCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.company_data['company']
        cls.country = cls.company.account_fiscal_country_id or cls.env.ref('base.us')
        cls.revenue = cls.company_data['default_account_revenue']
        cls.expense = cls.company_data['default_account_expense']
        cls.tax_sale = cls.company_data['default_tax_sale']

        cls.report = cls.env['account.report'].create({
            'name': 'Management P&L',
            'country_id': cls.country.id,
            'filter_date_range': True,
            'filter_period_comparison': True,
            'column_ids': [Command.create({'name': 'Balance', 'expression_label': 'balance'})],
        })
        Line = cls.env['account.report.line']

        def line(name, code, expressions, **values):
            return Line.create({
                'name': name, 'code': code, 'report_id': cls.report.id,
                'expression_ids': [Command.create({'label': 'balance', **expression}) for expression in expressions],
                **values,
            })

        cls.line_revenue = line('Revenue', 'REV', [
            {'engine': 'account_codes', 'formula': f'-{cls.revenue.code}'}])
        cls.line_expense = line('Expenses', 'EXP', [
            {'engine': 'domain', 'formula': str([('account_id', '=', cls.expense.id)]), 'subformula': 'sum'}])
        cls.line_net = line('Net', 'NET', [
            {'engine': 'aggregation', 'formula': 'REV.balance - EXP.balance'}])
        cls.line_big = line('Net if above 10000', 'BIG', [
            {'engine': 'aggregation', 'formula': 'NET.balance', 'subformula': 'if_above(CUR(10000))'}])
        cls.line_vat = line('Output VAT', 'VAT', [
            {'engine': 'tax_tags', 'formula': '-ci_test_output_vat'}])
        cls.line_manual = line('Manual adjustment', 'MAN', [
            {'engine': 'external', 'formula': 'sum', 'subformula': 'editable'}])
        cls.line_by_account = line('By account', 'BYACC', [
            {'engine': 'account_codes', 'formula': f'{cls.revenue.code}+{cls.expense.code}'}], groupby='account_id')
        cls.line_cumulative = line('Revenue to date', 'REVCUM', [
            {'engine': 'account_codes', 'formula': f'-{cls.revenue.code}', 'date_scope': 'from_beginning'}])
        cls.line_parent = line('Total', 'TOT', [{'engine': 'aggregation', 'formula': 'sum_children'}])
        line('Child revenue', 'CHREV', [{'engine': 'aggregation', 'formula': 'REV.balance'}],
             parent_id=cls.line_parent.id)
        line('Child expenses', 'CHEXP', [{'engine': 'aggregation', 'formula': '-EXP.balance'}],
             parent_id=cls.line_parent.id)

        # the tax tag created by the expression goes on the tax line of the sale tax
        tag = cls.env['account.account.tag'].search([
            ('name', '=', 'ci_test_output_vat'), ('country_id', '=', cls.country.id), ('applicability', '=', 'taxes')])
        tax_repartition = cls.tax_sale.invoice_repartition_line_ids.filtered(lambda r: r.repartition_type == 'tax')
        tax_repartition.tag_ids = [Command.link(tag.id)]

        cls.env['account.report.external.value'].create({
            'name': 'Adjustment', 'value': 50.0, 'date': '2025-06-30',
            'target_report_expression_id': cls.line_manual.expression_ids.id, 'company_id': cls.company.id,
        })
        cls._create_invoice_one_line(price_unit=1000.0, tax_ids=cls.tax_sale, invoice_date='2024-12-15',
                                     post=True)
        cls.invoice = cls._create_invoice_one_line(price_unit=2000.0, tax_ids=cls.tax_sale,
                                                   invoice_date='2025-03-10', post=True)
        cls._create_invoice_one_line(move_type='in_invoice', price_unit=500.0, tax_ids=cls.env['account.tax'],
                                     invoice_date='2025-04-01', post=True)

    def _info(self, report=None, **options):
        options.setdefault('date', {'filter': 'custom', 'date_from': '2025-01-01', 'date_to': '2025-12-31'})
        options['report_id'] = (report or self.report).id
        return self.env['ci.account.report.custom'].get_report_information(options)

    def _values(self, info):
        return {line['id']: [col['no_format'] for col in line['columns']] for line in info['lines']}

    def _rline(self, line):
        return f'rline-{line.id}'

    def test_engines(self):
        info = self._info(hide_zero=False)
        self.assertTrue(info['title'].startswith('Management P&L'))
        values = self._values(info)
        self.assertAlmostEqual(values[self._rline(self.line_revenue)][0], 2000.0)
        self.assertAlmostEqual(values[self._rline(self.line_expense)][0], 500.0)
        self.assertAlmostEqual(values[self._rline(self.line_net)][0], 1500.0)
        self.assertAlmostEqual(values[self._rline(self.line_big)][0], 0.0)
        self.assertAlmostEqual(values[self._rline(self.line_vat)][0], self.invoice.amount_tax)
        self.assertAlmostEqual(values[self._rline(self.line_manual)][0], 50.0)
        self.assertAlmostEqual(values[self._rline(self.line_cumulative)][0], 3000.0)
        self.assertAlmostEqual(values[self._rline(self.line_parent)][0], 1500.0)

    def test_groupby_lines(self):
        values = self._values(self._info())
        prefix = self._rline(self.line_by_account)
        self.assertAlmostEqual(values[f'{prefix}|grp-{self.revenue.id}'][0], -2000.0)
        self.assertAlmostEqual(values[f'{prefix}|grp-{self.expense.id}'][0], 500.0)

    def test_comparison_and_options(self):
        info = self._info(comparison={'filter': 'same_last_year', 'number_period': 1})
        self.assertIn('comparison', info['filters'])
        self.assertEqual(info['date_mode'], 'range')
        values = self._values(info)
        self.assertAlmostEqual(values[self._rline(self.line_revenue)][1], 1000.0)

    def test_cross_report(self):
        other = self.env['account.report'].create({
            'name': 'Summary',
            'column_ids': [Command.create({'name': 'Balance', 'expression_label': 'balance'})],
            'line_ids': [Command.create({
                'name': 'Net from P&L', 'code': 'SUMNET',
                'expression_ids': [Command.create({
                    'label': 'balance', 'engine': 'aggregation', 'formula': 'NET.balance',
                    'subformula': f'cross_report({self.report.id})',
                })],
            })],
        })
        values = self._values(self._info(report=other))
        self.assertAlmostEqual(values[self._rline(other.line_ids)][0], 1500.0)

    def test_drilldown(self):
        info = self._info()
        action = self.env['ci.account.report.custom'].action_open_line(
            info['options'], self._rline(self.line_revenue), 'journal_items')
        amls = self.env['account.move.line'].search(action['domain'])
        self.assertAlmostEqual(-sum(amls.mapped('balance')), 2000.0)

    def test_open_from_record_and_export(self):
        action = self.report.action_ci_open_report()
        self.assertEqual(action['context']['report_id'], self.report.id)
        content, filename = self.env['ci.account.report.custom'].export_to_xlsx(
            {'report_id': self.report.id, 'date': {'filter': 'custom', 'date_from': '2025-01-01',
                                                   'date_to': '2025-12-31'}})
        self.assertTrue(filename.startswith('Management_P&L'))
        self.assertTrue(content)
