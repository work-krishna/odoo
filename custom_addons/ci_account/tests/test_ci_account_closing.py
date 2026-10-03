# -*- coding: utf-8 -*-
from datetime import date

from odoo import Command
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged('post_install', '-at_install')
class TestCiAccountFiscalYear(AccountTestInvoicingCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.company_data['company']
        cls.FiscalYear = cls.env['ci.account.fiscal.year']

    def test_default_fiscal_year(self):
        dates = self.company.compute_fiscalyear_dates(date(2025, 5, 3))
        self.assertEqual((dates['date_from'], dates['date_to']), (date(2025, 1, 1), date(2025, 12, 31)))

    def test_explicit_fiscal_year_wins(self):
        # Nepali fiscal year 2083/84: 2026-07-17 to 2027-07-16
        self.FiscalYear.create({'name': '2083/84', 'date_from': '2026-07-17', 'date_to': '2027-07-16'})
        dates = self.company.compute_fiscalyear_dates(date(2026, 12, 1))
        self.assertEqual((dates['date_from'], dates['date_to']), (date(2026, 7, 17), date(2027, 7, 16)))
        # dates around it follow the day/month rule, cut where the record starts or ends
        before = self.company.compute_fiscalyear_dates(date(2026, 3, 1))
        self.assertEqual((before['date_from'], before['date_to']), (date(2026, 1, 1), date(2026, 7, 16)))
        after = self.company.compute_fiscalyear_dates(date(2027, 9, 1))
        self.assertEqual((after['date_from'], after['date_to']), (date(2027, 7, 17), date(2027, 12, 31)))

    def test_overlap_refused(self):
        self.FiscalYear.create({'name': 'FY1', 'date_from': '2025-01-01', 'date_to': '2025-12-31'})
        with self.assertRaises(ValidationError):
            self.FiscalYear.create({'name': 'FY2', 'date_from': '2025-06-01', 'date_to': '2026-05-31'})

    def test_create_next(self):
        last = self.FiscalYear.create({'name': '2083/84', 'date_from': '2026-07-17', 'date_to': '2027-07-16'})
        following = last.action_create_next()
        self.assertEqual((following.date_from, following.date_to), (date(2027, 7, 17), date(2028, 7, 16)))

    def test_reports_use_fiscal_years(self):
        self.FiscalYear.create({'name': '2083/84', 'date_from': '2026-07-17', 'date_to': '2027-07-16'})
        report = self.env['ci.account.report.profit.loss']
        date_from, date_to = report._ci_compute_period('this_year', date(2027, 1, 10))
        self.assertEqual((date_from, date_to), (date(2026, 7, 17), date(2027, 7, 16)))
        options = report._ci_get_options({'date': {'filter': 'this_year'}})
        self.assertTrue(options['date']['string'])


@tagged('post_install', '-at_install')
class TestCiAccountLockDates(AccountTestInvoicingCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.company_data['company']

    def _wizard(self, **values):
        wizard = self.env['ci.account.lock.date.wizard'].create({})
        wizard.write(values)
        return wizard

    def test_set_lock_dates(self):
        entry = self.env['account.move'].create({
            'journal_id': self.company_data['default_journal_misc'].id,
            'date': '2025-01-15',
            'line_ids': [
                Command.create({'account_id': self.company_data['default_account_revenue'].id, 'balance': -10.0}),
                Command.create({'account_id': self.company_data['default_account_expense'].id, 'balance': 10.0}),
            ],
        })
        entry.action_post()
        self._wizard(fiscalyear_lock_date='2025-01-31', sale_lock_date='2025-02-28').action_save()
        self.assertEqual(self.company.fiscalyear_lock_date, date(2025, 1, 31))
        self.assertEqual(self.company.sale_lock_date, date(2025, 2, 28))
        with self.assertRaises(UserError):
            entry.button_draft()

    def test_unlock_with_exception(self):
        self._wizard(fiscalyear_lock_date='2025-03-31').action_save()
        wizard = self._wizard(fiscalyear_lock_date='2025-01-31')
        self.assertTrue(wizard.is_loosening)
        wizard.write({'loosening_mode': 'exception', 'exception_user': 'me', 'exception_duration': '1h',
                      'exception_reason': 'Late bill'})
        wizard.action_save()
        # the company lock date did not move, an exception was recorded
        self.assertEqual(self.company.fiscalyear_lock_date, date(2025, 3, 31))
        exception = self.env['account.lock_exception'].search([('company_id', '=', self.company.id)])
        self.assertEqual(exception.lock_date_field, 'fiscalyear_lock_date')
        self.assertEqual(exception.user_id, self.env.user)
        self.assertEqual(self.company.user_fiscalyear_lock_date, date(2025, 1, 31))

    def test_unlock_permanently(self):
        self._wizard(fiscalyear_lock_date='2025-03-31').action_save()
        self._wizard(fiscalyear_lock_date=False, loosening_mode='permanent').action_save()
        self.assertFalse(self.company.fiscalyear_lock_date)

    def test_only_managers(self):
        user = self.env['res.users'].create({
            'name': 'Accountant', 'login': 'ci_accountant',
            'group_ids': [Command.set([self.env.ref('account.group_account_user').id])],
            'company_id': self.company.id, 'company_ids': [Command.set(self.company.ids)],
        })
        with self.assertRaises(AccessError):
            self.env['ci.account.lock.date.wizard'].with_user(user).create({}).action_save()

    def test_accountant_group_is_assignable(self):
        group = self.env.ref('account.group_account_user')
        self.assertEqual(group.privilege_id, self.env.ref('account.res_groups_privilege_accounting'))
        self.assertIn(group, self.env.ref('account.group_account_manager').implied_ids)


@tagged('post_install', '-at_install')
class TestCiAccountTaxClosing(AccountTestInvoicingCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.company_data['company']
        cls.tax_sale = cls.company_data['default_tax_sale']
        cls.tax_purchase = cls.company_data['default_tax_purchase']
        cls.payable = cls.env['account.account'].create({
            'code': '252099', 'name': 'VAT Payable (test)', 'account_type': 'liability_current', 'reconcile': True,
        })
        cls.receivable = cls.env['account.account'].create({
            'code': '132099', 'name': 'VAT Receivable (test)', 'account_type': 'asset_current', 'reconcile': True,
        })
        cls.invoice = cls._create_invoice_one_line(price_unit=1000.0, tax_ids=cls.tax_sale,
                                                   invoice_date='2025-03-10', post=True)
        cls.bill = cls._create_invoice_one_line(move_type='in_invoice', price_unit=400.0, tax_ids=cls.tax_purchase,
                                                invoice_date='2025-03-12', post=True)

    def _wizard(self):
        return self.env['ci.account.tax.closing.wizard'].create({
            'date_from': '2025-03-01', 'date_to': '2025-03-31',
            'payable_account_id': self.payable.id, 'receivable_account_id': self.receivable.id,
        })

    def test_closing_entry(self):
        wizard = self._wizard()
        expected_due = self.invoice.amount_tax - self.bill.amount_tax
        self.assertAlmostEqual(wizard.amount_due, expected_due)
        action = wizard.action_create_closing()
        move = self.env['account.move'].browse(action['res_id'])
        self.assertEqual(move.state, 'posted')
        self.assertEqual(move.ci_tax_closing_date_to, date(2025, 3, 31))
        # the tax accounts are emptied for the period
        tax_accounts = (self.tax_sale | self.tax_purchase).invoice_repartition_line_ids.account_id
        balances = self.env['account.move.line']._read_group(
            [('account_id', 'in', tax_accounts.ids), ('parent_state', '=', 'posted')], [], ['balance:sum'])
        self.assertAlmostEqual(balances[0][0], 0.0)
        tax_groups = (self.tax_sale | self.tax_purchase).tax_group_id
        closing_accounts = tax_groups.tax_payable_account_id | tax_groups.tax_receivable_account_id | self.payable \
            | self.receivable
        closing_balance = sum(move.line_ids.filtered(lambda l: l.account_id in closing_accounts).mapped('balance'))
        self.assertAlmostEqual(closing_balance, -expected_due)
        self.assertEqual(self.company.tax_lock_date, date(2025, 3, 31))

    def test_closing_twice_refused(self):
        self._wizard().action_create_closing()
        with self.assertRaises(UserError):
            self._wizard().action_create_closing()


@tagged('post_install', '-at_install')
class TestCiAccountEarningsAllocation(AccountTestInvoicingCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.company_data['company']
        cls.retained = cls.env['account.account'].create({
            'code': '310099', 'name': 'Retained Earnings (test)', 'account_type': 'equity',
        })
        cls._create_invoice_one_line(price_unit=1000.0, tax_ids=cls.env['account.tax'], invoice_date='2024-05-10',
                                     post=True)
        cls._create_invoice_one_line(move_type='in_invoice', price_unit=300.0, tax_ids=cls.env['account.tax'],
                                     invoice_date='2024-06-10', post=True)

    def test_allocation(self):
        unaffected = self.env['account.account'].search([
            ('company_ids', 'in', self.company.id), ('account_type', '=', 'equity_unaffected')], limit=1)
        if not unaffected:
            unaffected = self.company.get_unaffected_earnings_account()
        wizard = self.env['ci.account.earnings.allocation.wizard'].create({
            'date': '2024-12-31',
            'unaffected_account_id': unaffected.id,
            'retained_earnings_account_id': self.retained.id,
        })
        self.assertAlmostEqual(wizard.amount, 700.0)
        wizard.action_allocate()
        self.assertAlmostEqual(self.retained.current_balance, -700.0)
        # the balance sheet of 2025 now shows the 2024 profit in retained earnings
        info = self.env['ci.account.report.balance.sheet'].get_report_information(
            {'date': {'filter': 'custom', 'date_to': '2025-06-30'}})
        lines = {line['id']: line for line in info['lines']}
        self.assertAlmostEqual(lines['node-previous_years_earnings']['columns'][0]['no_format'], 0.0)
        self.assertAlmostEqual(lines['node-retained_earnings']['columns'][0]['no_format'], 700.0)
        # nothing left to allocate
        again = self.env['ci.account.earnings.allocation.wizard'].create({
            'date': '2024-12-31', 'unaffected_account_id': unaffected.id,
            'retained_earnings_account_id': self.retained.id,
        })
        self.assertAlmostEqual(again.amount, 0.0)
        with self.assertRaises(UserError):
            again.action_allocate()


@tagged('post_install', '-at_install')
class TestCiAccountNepaliFiscalYear(AccountTestInvoicingCommon):
    """Only meaningful when l10n_np_ird (Bikram Sambat calendar) is installed."""

    def test_nepali_fiscal_year_without_record(self):
        company = self.company_data['company']
        if 'l10n_np_bs_invoice_numbering' not in company._fields:
            self.skipTest("l10n_np_ird is not installed")
        company.account_fiscal_country_id = self.env.ref('base.np')
        dates = company.compute_fiscalyear_dates(date(2026, 12, 1))
        self.assertEqual((dates['date_from'], dates['date_to']), (date(2026, 7, 17), date(2027, 7, 16)))
        self.assertEqual(company._ci_fiscal_year_name(date(2026, 7, 17), date(2027, 7, 16)), '2083/84')
        created = self.env['ci.account.fiscal.year'].action_create_next()
        self.assertTrue(created.name.count('/') == 1)
