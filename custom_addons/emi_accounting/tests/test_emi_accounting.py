# -*- coding: utf-8 -*-
import base64
from datetime import date

from dateutil.relativedelta import relativedelta

from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged
from odoo.tests.common import new_test_user

from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.addons.emi_accounting.tools.amortization import build_schedule, flat_effective_monthly_rate

DOC = base64.b64encode(b'doc')


@tagged('post_install', '-at_install')
class TestAmortization(AccountTestInvoicingCommon):

    def test_flat_rate_uses_effective_interest(self):
        lines = build_schedule(90000, 7, 18, 'flat', date(2026, 9, 24))
        self.assertEqual(len(lines), 18)
        self.assertAlmostEqual(sum(l['principal_amount'] for l in lines), 90000, places=2)
        self.assertAlmostEqual(sum(l['interest_amount'] for l in lines), 9450, places=2)  # flat quote
        self.assertTrue(all(l['amount'] == 5525.0 for l in lines))
        # effective interest front-loads interest on the larger balance
        self.assertGreater(lines[0]['interest_amount'], lines[-1]['interest_amount'])
        self.assertEqual(lines[-1]['closing_balance'], 0.0)
        self.assertEqual(lines[0]['due_date'], date(2026, 10, 24))

    def test_reducing_and_zero(self):
        reducing = build_schedule(90000, 7, 18, 'reducing', date(2026, 1, 31))
        self.assertAlmostEqual(reducing[0]['amount'], 5281.65, places=2)
        self.assertAlmostEqual(reducing[0]['interest_amount'], 525.0, places=2)
        self.assertEqual(reducing[0]['due_date'], date(2026, 2, 28))
        zero = build_schedule(90000, 0, 12, 'flat', date(2026, 1, 1))
        self.assertTrue(all(l['interest_amount'] == 0 for l in zero))
        self.assertAlmostEqual(sum(l['amount'] for l in zero), 90000, places=2)

    def test_effective_rate_solver(self):
        rate = flat_effective_monthly_rate(90000, 5525.0, 18)
        pv = 5525.0 * (1 - (1 + rate) ** -18) / rate
        self.assertAlmostEqual(pv, 90000, places=4)


@tagged('post_install', '-at_install')
class TestEmiAccountingFlow(AccountTestInvoicingCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env(su=True)  # EMI configuration; the flow itself runs as the EMI users
        cls.marketplace = cls.company_data['company']
        env['res.company'].search([('emi_is_marketplace', '=', True)]).emi_is_marketplace = False
        cls.marketplace.emi_is_marketplace = True
        cls.lender_data = cls.setup_other_company(name='Lender Finance Ltd')
        cls.lender = cls.lender_data['company']

        cls.plan_18 = env.ref('emi_finance.tenure_plan_18')
        cls.finance = env['emi.finance.company'].create({'code': 'LFL', 'company_id': cls.lender.id})
        env['emi.interest.rate'].create({
            'finance_company_id': cls.finance.id, 'tenure_plan_id': cls.plan_18.id,
            'rate_percent': 7.0, 'calc_method': 'flat', 'date_from': '2020-01-01',
        })
        (cls.marketplace | cls.lender).action_emi_setup_accounting()

        cls.officer = new_test_user(
            env, 'acc_officer', groups='emi_finance.group_emi_officer',
            company_id=cls.marketplace.id, company_ids=[(6, 0, cls.marketplace.ids)],
        )
        cls.reviewer = new_test_user(
            env, 'acc_reviewer', groups='emi_finance.group_emi_finance_reviewer',
            company_id=cls.lender.id, company_ids=[(6, 0, cls.lender.ids)],
        )
        cls.mp_admin = new_test_user(
            env, 'acc_mp_admin', groups='emi_marketplace.group_emi_marketplace_admin',
            company_id=cls.marketplace.id, company_ids=[(6, 0, cls.marketplace.ids)],
        )

        vendor_partner = env['res.partner'].create({'name': 'Retailer One', 'is_company': True})
        bank = env['res.partner.bank'].create({'acc_number': 'NP-RET-1', 'partner_id': vendor_partner.id})
        cls.vendor = env['emi.vendor'].create({
            'partner_id': vendor_partner.id, 'settlement_bank_account_id': bank.id,
            'commission_type': 'percent', 'commission_value': 5.0,
        })
        cls.vendor.onboarding_document_ids = [(0, 0, {
            'name': 'reg.pdf', 'datas': DOC, 'res_model': 'emi.vendor', 'res_id': cls.vendor.id,
        })]
        cls.vendor.action_submit()
        cls.vendor.action_approve()
        tmpl = env['product.template'].create({'name': 'Phone X', 'list_price': 100000.0, 'vendor_id': cls.vendor.id})
        tmpl.action_submit_listing()
        tmpl.action_publish_listing()
        cls.phone = tmpl.product_variant_id
        cls.customer = env['res.partner'].create({'name': 'Sita Customer'})

    def _approved_application(self):
        app = self.env['emi.application'].with_user(self.officer).create({
            'partner_id': self.customer.id, 'product_id': self.phone.id,
            'finance_company_id': self.finance.id, 'tenure_plan_id': self.plan_18.id,
            'down_payment_amount': 10000.0, 'delivery_note': 'Shop pickup',
            'kyc_ids': [(0, 0, {
                'full_name': 'Sita', 'date_of_birth': '1992-02-02', 'phone': '98', 'citizenship_no': 'C-1',
                'permanent_address': 'Pokhara', 'occupation': 'salaried', 'monthly_income': 60000,
                'citizenship_front': DOC, 'citizenship_back': DOC, 'photo': DOC, 'income_proof': DOC,
            })],
        })
        officer_app = app.with_user(self.officer)
        officer_app.action_submit()
        officer_app.action_start_review()
        officer_app.action_verify_kyc()
        officer_app.action_send_to_finance()
        app.with_user(self.reviewer).action_approve()
        return app

    def _pay_installment(self, app, amount, user=None, journal=None):
        user = user or self.reviewer
        journal = journal or self.lender_data['default_journal_bank']
        wizard = self.env['emi.installment.payment'].with_user(user).create({
            'application_id': app.id, 'amount': amount, 'journal_id': journal.id,
        })
        wizard.action_confirm()

    def _balance(self, account, partner=None):
        domain = [('account_id', '=', account.id), ('parent_state', '=', 'posted')]
        if partner:
            domain.append(('partner_id', '=', partner.id))
        return sum(self.env['account.move.line'].search(domain).mapped('balance'))

    def test_disbursement_books_both_companies_and_schedule(self):
        app = self._approved_application()
        self.env['emi.down.payment'].with_user(self.officer).create({
            'application_id': app.id, 'journal_id': self.company_data['default_journal_bank'].id,
        }).action_confirm()

        with self.assertRaises(AccessError):
            app.with_user(self.officer).action_disburse()
        app.with_user(self.reviewer).action_disburse()
        self.assertEqual(app.state, 'disbursed')

        # Lender: loan principal receivable from the customer.
        self.assertEqual(app.finance_move_id.company_id, self.lender)
        self.assertAlmostEqual(self._balance(self.lender.emi_loan_account_id, self.customer), 90000.0)
        # Marketplace: whole price held for the retailer; down payment matched.
        self.assertEqual(app.marketplace_move_id.company_id, self.marketplace)
        vendor_partner = self.vendor.partner_id
        self.assertAlmostEqual(self._balance(self.marketplace.emi_vendor_clearing_account_id, vendor_partner), -100000.0)
        customer_lines = app.marketplace_move_id.line_ids.filtered(lambda l: l.partner_id == self.customer)
        self.assertTrue(customer_lines.reconciled)
        # Commission invoice to the retailer: 5% of 100,000 + VAT.
        invoice = app.commission_invoice_id
        self.assertEqual(invoice.move_type, 'out_invoice')
        self.assertEqual(invoice.partner_id, vendor_partner)
        self.assertEqual(invoice.state, 'posted')
        self.assertAlmostEqual(invoice.amount_untaxed, 5000.0)
        # Schedule: flat 7% for 18 months on 90,000.
        lines = app.schedule_line_ids
        self.assertEqual(len(lines), 18)
        self.assertAlmostEqual(sum(lines.mapped('principal_amount')), 90000.0)
        self.assertAlmostEqual(sum(lines.mapped('interest_amount')), 9450.0)
        self.assertEqual(lines[0].due_date, app.disbursement_date + relativedelta(months=1))

    def test_finance_company_collects_installments_until_close(self):
        app = self._approved_application()
        app.with_user(self.reviewer).action_disburse()
        first = app.schedule_line_ids[0]
        self._pay_installment(app, first.amount)
        self.assertEqual(first.state, 'paid')
        self.assertEqual(app.state, 'active')
        self.assertAlmostEqual(-self._balance(self.lender.emi_interest_income_account_id), first.interest_amount)
        self.assertAlmostEqual(self._balance(self.lender.emi_loan_account_id, self.customer),
                               90000.0 - first.principal_amount)

        with self.assertRaises(UserError):
            app.with_user(self.officer).action_close()
        self._pay_installment(app, app.amount_outstanding)
        self.assertTrue(all(line.state == 'paid' for line in app.schedule_line_ids))
        self.assertAlmostEqual(self._balance(self.lender.emi_loan_account_id, self.customer), 0.0)
        self.assertAlmostEqual(-self._balance(self.lender.emi_interest_income_account_id), 9450.0)
        app.with_user(self.officer).action_close()
        self.assertEqual(app.state, 'closed')

    def test_marketplace_collects_and_owes_lender(self):
        self.finance.sudo().installment_collection = 'marketplace'
        app = self._approved_application()
        app.with_user(self.reviewer).action_disburse()
        first = app.schedule_line_ids[0]
        with self.assertRaises(AccessError):  # reviewer does not work for the marketplace
            self._pay_installment(app, first.amount, user=self.reviewer)
        self._pay_installment(app, first.amount, user=self.officer, journal=self.company_data['default_journal_bank'])
        self.assertEqual(first.state, 'paid')
        lender_partner = self.lender.partner_id
        payable_to_lender = lender_partner.with_company(self.marketplace).property_account_payable_id
        self.assertAlmostEqual(self._balance(payable_to_lender, lender_partner), -first.amount)
        marketplace_partner = self.marketplace.partner_id
        receivable_from_mp = marketplace_partner.with_company(self.lender).property_account_receivable_id
        self.assertAlmostEqual(self._balance(receivable_from_mp, marketplace_partner), first.amount)

    def test_overpayment_rejected(self):
        app = self._approved_application()
        app.with_user(self.reviewer).action_disburse()
        with self.assertRaises(UserError):
            self._pay_installment(app, 1_000_000.0)

    def test_due_installments_posted_by_cron(self):
        app = self._approved_application()
        app.with_user(self.reviewer).action_disburse()
        line = app.schedule_line_ids[0]
        line.sudo().due_date = '2020-01-01'
        self.env['emi.schedule.line']._cron_post_due_installments()
        self.assertTrue(line.due_move_id)
        self.assertEqual(line.due_move_id.state, 'posted')
        self.assertEqual(line.state, 'overdue')
        self.assertFalse(app.schedule_line_ids[1].due_move_id)

    def test_retailer_settlement_nets_commission(self):
        app = self._approved_application()
        self.env['emi.down.payment'].with_user(self.officer).create({
            'application_id': app.id, 'journal_id': self.company_data['default_journal_bank'].id,
        }).action_confirm()
        app.with_user(self.reviewer).action_disburse()
        Settlement = self.env['emi.vendor.settlement']
        # Financing not yet received from the lender: nothing to settle.
        self.assertFalse(Settlement._create_for_vendor(self.vendor))

        lender_partner = self.lender.partner_id
        payment = self.env['account.payment'].with_company(self.marketplace).create({
            'payment_type': 'inbound', 'partner_type': 'customer', 'partner_id': lender_partner.id,
            'amount': 90000.0, 'journal_id': self.company_data['default_journal_bank'].id,
        })
        payment.action_post()
        (payment.move_id.line_ids | app.marketplace_move_id.line_ids).filtered(
            lambda l: l.partner_id == lender_partner and l.account_id.account_type == 'asset_receivable'
        ).reconcile()

        settlement = Settlement._create_for_vendor(self.vendor)
        commission_total = app.commission_invoice_id.amount_total
        self.assertAlmostEqual(settlement.gross_amount, 100000.0)
        self.assertAlmostEqual(settlement.commission_amount, commission_total)
        self.assertAlmostEqual(settlement.net_amount, 100000.0 - commission_total)
        settlement.action_post()
        self.assertEqual(settlement.state, 'posted')
        self.assertEqual(app.commission_invoice_id.payment_state, 'paid')
        vendor_partner = self.vendor.partner_id
        self.assertAlmostEqual(self._balance(self.marketplace.emi_vendor_clearing_account_id, vendor_partner), 0.0)
        payable = vendor_partner.with_company(self.marketplace).property_account_payable_id
        self.assertAlmostEqual(self._balance(payable, vendor_partner), -(100000.0 - commission_total))
        self.assertEqual(settlement.payment_state, 'not_paid')
        # A second run finds nothing new.
        self.assertFalse(Settlement._create_for_vendor(self.vendor))

    def test_missing_configuration_is_reported(self):
        self.lender.sudo().emi_loan_account_id = False
        app = self._approved_application()
        with self.assertRaisesRegex(UserError, 'EMI Loans Receivable'):
            app.with_user(self.reviewer).action_disburse()
        self.assertEqual(app.state, 'approved')
