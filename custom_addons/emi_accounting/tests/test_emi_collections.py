# -*- coding: utf-8 -*-
from datetime import timedelta

from freezegun import freeze_time

from odoo import fields
from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged
from odoo.tests.common import new_test_user

from odoo.addons.emi_accounting.tools.amortization import effective_monthly_rate

from .common import EmiAccountingCommon


@tagged('post_install', '-at_install')
class TestEmiDownPayments(EmiAccountingCommon):

    def test_down_payment_due_ignores_marketplace_installments(self):
        """Installments the marketplace collects are not down payments."""
        self.finance.sudo().installment_collection = 'marketplace'
        app = self._approved_application()
        app.with_user(self.reviewer).action_disburse()  # before the down payment arrived
        self._bill(app, 2)
        for line in app.schedule_line_ids.sorted('number')[:2]:
            self._pay_installment(app, line.amount, user=self.officer, journal=self.company_data['default_journal_bank'])
        self.assertEqual(app._emi_amount_due('down_payment'), 10000.0)
        self._pay_down_payment(app)
        self.assertEqual(app._emi_amount_due('down_payment'), 0.0)
        self.assertTrue(app.marketplace_move_id.line_ids.filtered(lambda l: l.partner_id == self.customer).reconciled)

    def test_down_payment_is_capped_at_what_is_due(self):
        app = self._approved_application()
        self._pay_down_payment(app, 4000.0)
        wizard = self.env['emi.down.payment'].with_user(self.officer).create({
            'application_id': app.id, 'journal_id': self.company_data['default_journal_bank'].id,
        })
        self.assertEqual(wizard.amount, 6000.0)
        wizard.action_confirm()
        self.assertEqual(app._emi_amount_due('down_payment'), 0.0)
        with self.assertRaises(UserError):
            self._pay_down_payment(app, 10000.0)
        self.assertEqual(app.down_payment_received, 10000.0)

    def test_down_payment_held_protects_the_application(self):
        app = self._submitted_application()
        self._pay_down_payment(app)
        officer_app = app.with_user(self.officer)
        officer_app.action_start_review()
        officer_app.action_return_to_draft()
        with self.assertRaises(UserError):
            officer_app.down_payment_amount = 0.0
        with self.assertRaises(UserError):
            officer_app.partner_id = self.env['res.partner'].sudo().create({'name': 'Someone Else'})
        officer_app.down_payment_amount = 12000.0  # asking for more is fine
        officer_app.action_submit()
        officer_app.action_start_review()
        officer_app.action_reject("Income could not be verified")
        with self.assertRaises(UserError):
            app.sudo().unlink()

        refund = self.env['emi.down.payment.refund'].with_user(self.officer).create({
            'application_id': app.id, 'journal_id': self.company_data['default_journal_bank'].id,
        })
        self.assertEqual(refund.amount, 10000.0)
        refund.action_confirm()
        self.assertEqual(app.down_payment_received, 0.0)
        receivable = self.customer.with_company(self.marketplace).property_account_receivable_id
        self.assertAlmostEqual(self._balance(receivable, self.customer), 0.0)
        self.assertFalse(self.env['account.move.line'].search([
            ('partner_id', '=', self.customer.id), ('account_id', '=', receivable.id), ('reconciled', '=', False),
        ]))


@tagged('post_install', '-at_install')
class TestEmiInstallments(EmiAccountingCommon):

    def test_early_payment_is_held_as_advance(self):
        """Nothing is posted ahead of its due date (no early interest income),
        including for amounts that are exact sums of installments."""
        plan_6 = self.env.ref('emi_finance.tenure_plan_6')
        self.env['emi.interest.rate'].sudo().create({
            'finance_company_id': self.finance.id, 'tenure_plan_id': plan_6.id,
            'rate_percent': 7.0, 'calc_method': 'reducing', 'date_from': '2020-01-01',
        })
        app = self._approved_application(plan_6)
        app.with_user(self.reviewer).action_disburse()
        lines = app.schedule_line_ids.sorted('number')
        self.assertEqual(lines[0].amount, 15307.73)
        three = round(sum(lines[:3].mapped('amount')), 2)
        self._pay_installment(app, three)
        self.assertFalse(lines.due_move_id)
        self.assertEqual(set(lines.mapped('state')), {'upcoming'})
        interest = self.lender.emi_interest_income_account_id
        self.assertAlmostEqual(self._balance(interest), 0.0)
        self.assertAlmostEqual(app.advance_amount, three)
        self.assertAlmostEqual(app.amount_outstanding, round(sum(lines.mapped('amount')) - three, 2))
        self.assertEqual(app._emi_amount_due('installment'), lines[3].amount)
        self.assertEqual(app.next_due_date, lines[3].due_date)

        # Each installment is settled from the advance when the cron posts it.
        self._bill(app, 3)
        self.assertEqual(lines[:3].mapped('state'), ['paid'] * 3)
        self.assertEqual(lines[3].state, 'upcoming')
        self.assertFalse(lines[3].due_move_id)
        self.assertAlmostEqual(app.advance_amount, 0.0)
        self.assertAlmostEqual(-self._balance(interest), sum(lines[:3].mapped('interest_amount')))

    def test_partly_paid_late_installment_stays_overdue(self):
        app = self._approved_application()
        app.with_user(self.reviewer).action_disburse()
        first = self._bill(app, 1)
        self._pay_installment(app, 1.0)
        self.assertEqual(first.state, 'overdue')
        self.assertAlmostEqual(app.overdue_amount, first.amount - 1.0)

        second = app.schedule_line_ids.sorted('number')[1]
        second.sudo().due_date = fields.Date.today()
        self.env['emi.schedule.line']._cron_post_due_installments()
        self._pay_installment(app, first.amount)  # the rest of the first, 1.0 of the second
        self.assertEqual(second.state, 'partial')
        with freeze_time(fields.Date.today() + timedelta(days=1)):
            self.env['emi.schedule.line']._cron_refresh_overdue()
        self.assertEqual(second.state, 'overdue')

    def test_cancelled_installment_entry_is_posted_again(self):
        """Entries cancelled before they were protected (older databases) are billed again."""
        app = self._approved_application()
        app.with_user(self.reviewer).action_disburse()
        first = self._bill(app, 1)
        cancelled = first.due_move_id
        cancelled.with_context(emi_reversal=True).button_cancel()
        self.env['emi.schedule.line']._cron_post_due_installments()
        self.assertNotEqual(first.due_move_id, cancelled)
        self.assertEqual(first.due_move_id.state, 'posted')
        self._pay_installment(app, first.amount)
        self.assertEqual(first.state, 'paid')

    def test_payment_journal_in_another_currency_is_refused(self):
        other_currency = self.setup_other_currency('EUR')
        journal = self.env['account.journal'].sudo().create({
            'name': 'EUR Bank', 'code': 'EURB', 'type': 'bank', 'company_id': self.lender.id,
            'currency_id': other_currency.id,
        })
        app = self._approved_application()
        app.with_user(self.reviewer).action_disburse()
        first = self._bill(app, 1)
        with self.assertRaises(UserError):
            self._pay_installment(app, first.amount, journal=journal)
        payment = self._pay_installment(app, first.amount)
        self.assertEqual(payment.currency_id, app.currency_id)
        self.assertEqual(first.state, 'paid')

    def test_early_settlement(self):
        """Payoff = principal left + interest accrued to date, pro rata by days."""
        app = self._approved_application()
        app.with_user(self.reviewer).action_disburse()
        start = app.disbursement_date
        period = (app.schedule_line_ids.sorted('number')[0].due_date - start).days
        interest = round(90000.0 * effective_monthly_rate(90000.0, 7.0, 18, 'flat') * 15 / period, 2)
        with freeze_time(start + timedelta(days=15)):
            self._pay_installment(app, 5000.0)  # paid ahead: goes to the payoff
            wizard = self.env['emi.foreclosure'].with_user(self.reviewer).create({'application_id': app.id})
            self.assertAlmostEqual(wizard.principal_amount, 90000.0)
            self.assertAlmostEqual(wizard.interest_amount, interest)
            with self.assertRaises(AccessError):
                app.with_user(self.officer).action_emi_foreclose()
            wizard.action_confirm()
        lines = app.schedule_line_ids.sorted('number')
        payoff = lines.filtered('is_foreclosure')
        self.assertEqual((lines - payoff).mapped('state'), ['settled'] * 18)
        self.assertAlmostEqual(payoff.amount, 90000.0 + interest)
        self.assertEqual(payoff.due_move_id.state, 'posted')
        self.assertAlmostEqual(payoff.amount_residual, 90000.0 + interest - 5000.0)
        self.assertAlmostEqual(app.amount_outstanding, 90000.0 + interest - 5000.0)
        self.assertAlmostEqual(-self._balance(self.lender.emi_interest_income_account_id), interest)

        self._pay_installment(app, app.amount_outstanding)
        self.assertEqual(payoff.state, 'paid')
        self.assertAlmostEqual(self._balance(self.lender.emi_loan_account_id, self.customer), 0.0)
        app.with_user(self.officer).action_close()
        self.assertEqual(app.state, 'closed')


@tagged('post_install', '-at_install')
class TestEmiReversals(EmiAccountingCommon):

    def test_emi_entries_cannot_be_undone_directly(self):
        app = self._approved_application()
        self._pay_down_payment(app)
        app.with_user(self.reviewer).action_disburse()
        first = self._bill(app, 1)
        payment = self._pay_installment(app, first.amount)
        for move in (app.finance_move_id, app.marketplace_move_id, first.due_move_id, app.commission_invoice_id):
            with self.assertRaises(UserError):
                move.button_draft()
            with self.assertRaises(UserError):
                move._reverse_moves(cancel=True)
        reversal = self.env['account.move.reversal'].with_context(
            active_model='account.move', active_ids=first.due_move_id.ids,
        ).create({'journal_id': first.due_move_id.journal_id.id, 'date': fields.Date.today()})
        with self.assertRaises(UserError):
            reversal.refund_moves()
        with self.assertRaises(UserError):
            payment.action_draft()
        with self.assertRaises(UserError):
            payment.action_cancel()
        self.assertEqual(first.state, 'paid')
        self.assertEqual(app.state, 'active')

    def test_cancel_disbursement(self):
        app = self._approved_application()
        self._pay_down_payment(app)
        app.with_user(self.reviewer).action_disburse()
        self._bill(app, 1)
        commission = app.commission_invoice_id
        with self.assertRaises(AccessError):
            app.with_user(self.officer).action_emi_cancel_disbursement()
        app.with_user(self.reviewer).action_emi_cancel_disbursement()

        self.assertEqual(app.state, 'approved')
        self.assertFalse(app.schedule_line_ids or app.disbursement_date or app.finance_move_id
                         or app.marketplace_move_id or app.commission_invoice_id)
        credit_note = self.env['account.move'].search([('reversed_entry_id', '=', commission.id)])
        self.assertEqual(credit_note.move_type, 'out_refund')
        self.assertEqual(credit_note.state, 'posted')
        self.assertEqual(commission.payment_state, 'reversed')
        lender_receivable = self.customer.with_company(self.lender).property_account_receivable_id
        self.assertAlmostEqual(self._balance(self.lender.emi_loan_account_id, self.customer), 0.0)
        self.assertAlmostEqual(self._balance(lender_receivable, self.customer), 0.0)
        self.assertAlmostEqual(
            self._balance(self.marketplace.emi_vendor_clearing_account_id, self.vendor.partner_id), 0.0)
        self.assertEqual(app.down_payment_received, 10000.0)  # still held for the next disbursement
        self.assertEqual(app._emi_amount_due('down_payment'), 0.0)

        app.with_user(self.reviewer).action_disburse()
        self.assertEqual(len(app.schedule_line_ids), 18)
        self.assertTrue(app.marketplace_move_id.line_ids.filtered(lambda l: l.partner_id == self.customer).reconciled)

    def test_cancel_disbursement_after_installment_payments(self):
        app = self._approved_application()
        app.with_user(self.reviewer).action_disburse()
        first = self._bill(app, 1)
        payment = self._pay_installment(app, first.amount)
        with self.assertRaises(UserError):
            app.with_user(self.reviewer).action_emi_cancel_disbursement()
        payment.with_user(self.reviewer).action_emi_reverse()
        self.assertEqual(payment.state, 'canceled')
        self.assertEqual(first.state, 'overdue')
        app.with_user(self.reviewer).action_emi_cancel_disbursement()
        self.assertEqual(app.state, 'approved')

    def test_reverse_marketplace_installment_receipt(self):
        self.finance.sudo().installment_collection = 'marketplace'
        app = self._approved_application()
        app.with_user(self.reviewer).action_disburse()
        first = self._bill(app, 1)
        payment = self._pay_installment(app, first.amount, user=self.officer,
                                        journal=self.company_data['default_journal_bank'])
        self.assertEqual(first.state, 'paid')
        with self.assertRaises(AccessError):  # the lender's reviewer does not work for the marketplace
            payment.with_user(self.reviewer).action_emi_reverse()
        payment.with_user(self.officer).action_emi_reverse()

        self.assertEqual(payment.state, 'canceled')
        linked = self.env['account.move'].search([('emi_receipt_id', '=', payment.id)])
        self.assertEqual(len(linked), 2)
        self.assertEqual(set(linked.mapped('state')), {'cancel'})
        self.assertEqual(first.state, 'overdue')
        lender_partner, marketplace_partner = self.lender.partner_id, self.marketplace.partner_id
        payable_to_lender = lender_partner.with_company(self.marketplace).property_account_payable_id
        self.assertAlmostEqual(self._balance(payable_to_lender, lender_partner), 0.0)
        receivable_from_mp = marketplace_partner.with_company(self.lender).property_account_receivable_id
        self.assertAlmostEqual(self._balance(receivable_from_mp, marketplace_partner), 0.0)


@tagged('post_install', '-at_install')
class TestEmiSettlements(EmiAccountingCommon):

    def _collected_sale(self):
        app = self._approved_application()
        self._pay_down_payment(app)
        app.with_user(self.reviewer).action_disburse()
        self._receive_financing(app)
        return app

    def test_reverse_settlement(self):
        app = self._collected_sale()
        Settlement = self.env['emi.vendor.settlement']
        settlement = Settlement._create_for_vendor(self.vendor)
        settlement.action_post()
        with self.assertRaises(UserError):
            settlement.move_id.button_draft()
        with self.assertRaises(UserError):
            settlement.move_id._reverse_moves(cancel=True)

        settlement.action_reverse()
        self.assertEqual(settlement.state, 'cancel')
        self.assertEqual(settlement.payment_state, 'not_paid')
        self.assertEqual(app.commission_invoice_id.payment_state, 'not_paid')
        vendor_partner = self.vendor.partner_id
        self.assertAlmostEqual(self._balance(self.marketplace.emi_vendor_clearing_account_id, vendor_partner),
                               -100000.0)
        again = Settlement._create_for_vendor(self.vendor)
        self.assertAlmostEqual(again.gross_amount, 100000.0)
        self.assertAlmostEqual(again.commission_amount, app.commission_invoice_id.amount_total)

    def test_settlement_never_nets_more_than_collected(self):
        self.vendor.sudo().commission_value = 95.0  # with VAT, above the sale price
        app = self._collected_sale()
        invoice = app.commission_invoice_id
        self.assertGreater(invoice.amount_total, 100000.0)
        settlement = self.env['emi.vendor.settlement']._create_for_vendor(self.vendor)
        self.assertAlmostEqual(settlement.commission_amount, 100000.0)
        self.assertAlmostEqual(settlement.net_amount, 0.0)
        settlement.action_post()
        self.assertEqual(settlement.payment_state, 'paid')
        vendor_partner = self.vendor.partner_id
        payable = vendor_partner.with_company(self.marketplace).property_account_payable_id
        self.assertAlmostEqual(self._balance(payable, vendor_partner), 0.0)
        self.assertAlmostEqual(invoice.amount_residual, invoice.amount_total - 100000.0)
        _collections, commissions = self.env['emi.vendor.settlement']._collect_open_lines(
            self.vendor, self.marketplace, True)
        self.assertEqual(commissions.move_id, invoice)  # the rest waits for the next settlement


@tagged('post_install', '-at_install')
class TestEmiAccountingAccess(EmiAccountingCommon):

    def test_billing_users_only_see_their_companies(self):
        app = self._approved_application()
        app.with_user(self.reviewer).action_disburse()
        env = self.env(su=True)
        other = env['res.company'].create({'name': 'Other Lender Ltd'})
        billing = 'account.group_account_invoice'
        outsider = new_test_user(env, 'acc_other_billing', groups=billing,
                                 company_id=other.id, company_ids=[(6, 0, other.ids)])
        lender_accountant = new_test_user(env, 'acc_lender_billing', groups=billing,
                                          company_id=self.lender.id, company_ids=[(6, 0, self.lender.ids)])
        mp_accountant = new_test_user(env, 'acc_mp_billing', groups=billing,
                                      company_id=self.marketplace.id, company_ids=[(6, 0, self.marketplace.ids)])
        Line = self.env['emi.schedule.line']
        domain = [('application_id', '=', app.id)]
        self.assertFalse(Line.with_user(outsider).search(domain))
        self.assertEqual(len(Line.with_user(lender_accountant).search(domain)), 18)
        self.assertEqual(len(Line.with_user(mp_accountant).search(domain)), 18)

        Vendor = self.env['emi.vendor']
        self.assertFalse(Vendor.with_user(outsider).search([('id', '=', self.vendor.id)]))
        self.assertTrue(Vendor.with_user(mp_accountant).search([('id', '=', self.vendor.id)]))
        self.assertTrue(Vendor.with_user(self.officer).search([('id', '=', self.vendor.id)]))
