# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import UserError

from odoo.addons.emi_accounting.tools.amortization import build_schedule
from odoo.addons.emi_application.models.application import REVIEWER, EmiApplication as BaseApplication


class EmiApplication(models.Model):
    _inherit = 'emi.application'

    _EMI_SERVER_FIELDS = BaseApplication._EMI_SERVER_FIELDS | {
        'schedule_line_ids', 'disbursement_date', 'finance_move_id', 'marketplace_move_id',
        'commission_invoice_id', 'commission_amount',
    }

    schedule_line_ids = fields.One2many('emi.schedule.line', 'application_id', string='Installments', readonly=True)
    disbursement_date = fields.Date(readonly=True, copy=False)
    finance_move_id = fields.Many2one(
        'account.move', string='Loan Entry', readonly=True, copy=False,
        help="Finance company: loan receivable against the customer, payable to the marketplace.",
    )
    marketplace_move_id = fields.Many2one(
        'account.move', string='Collection Entry', readonly=True, copy=False,
        help="Marketplace: down payment due from the customer and financing due from the finance "
             "company, held for the retailer.",
    )
    commission_invoice_id = fields.Many2one('account.move', string='Commission Invoice', readonly=True, copy=False)
    commission_amount = fields.Monetary(readonly=True, copy=False, help="Marketplace commission, excluding VAT.")
    installments_paid = fields.Integer(compute='_compute_installment_summary')
    amount_outstanding = fields.Monetary(
        string='Outstanding Balance', compute='_compute_installment_summary',
        help="Installments not yet paid, including those not yet due.",
    )
    next_due_date = fields.Date(compute='_compute_installment_summary')
    overdue_amount = fields.Monetary(compute='_compute_installment_summary')

    @api.depends('schedule_line_ids.state', 'schedule_line_ids.amount_residual')
    def _compute_installment_summary(self):
        for app in self:
            lines = app.schedule_line_ids
            open_lines = lines.filtered(lambda l: l.state != 'paid')
            app.installments_paid = len(lines) - len(open_lines)
            app.amount_outstanding = sum(open_lines.mapped('amount_residual'))
            app.next_due_date = min(open_lines.mapped('due_date'), default=False)
            app.overdue_amount = sum(open_lines.filtered(lambda l: l.state == 'overdue').mapped('amount_residual'))

    # ------------------------------------------------------------------
    # Disbursement
    # ------------------------------------------------------------------

    def _emi_commission(self):
        self.ensure_one()
        vendor = self.vendor_id.sudo()
        if vendor.commission_type == 'fixed':
            amount = vendor.currency_id._convert(
                vendor.commission_value, self.currency_id, self.company_id, fields.Date.context_today(self),
            )
        else:
            amount = self.list_price * vendor.commission_value / 100.0
        return self.currency_id.round(amount)

    def _emi_check_ready_to_disburse(self):
        self.ensure_one()
        marketplace = self.company_id.sudo()
        lender = self.finance_company_id.company_id.sudo()
        marketplace._emi_check_accounting('marketplace')
        lender._emi_check_accounting('finance')
        if lender.currency_id != self.currency_id:
            raise UserError(
                f"{lender.name} keeps its books in {lender.currency_id.name} but the application is in "
                f"{self.currency_id.name}; EMI loans must use the same currency."
            )
        if not self.vendor_id:
            raise UserError("The application has no retailer to hold the collection for.")

    def _emi_create_finance_move(self, date):
        """Lender books: loan receivable (customer) against payable to the marketplace."""
        self.ensure_one()
        lender = self.finance_company_id.company_id.sudo()
        customer = self.partner_id.commercial_partner_id
        marketplace_partner = self.company_id.partner_id
        payable = marketplace_partner.with_company(lender).property_account_payable_id
        move = self.env['account.move'].sudo().with_company(lender).create({
            'move_type': 'entry',
            'journal_id': lender.emi_journal_id.id,
            'date': date,
            'ref': f"{self.name} disbursement",
            'emi_application_id': self.id,
            'line_ids': [
                (0, 0, {'name': f"{self.name} loan principal", 'account_id': lender.emi_loan_account_id.id,
                        'partner_id': customer.id, 'debit': self.financed_amount}),
                (0, 0, {'name': f"{self.name} disbursement to {self.company_id.name}", 'account_id': payable.id,
                        'partner_id': marketplace_partner.id, 'credit': self.financed_amount}),
            ],
        })
        move.action_post()
        return move

    def _emi_create_marketplace_move(self, date):
        """Marketplace books (agent for the retailer): the customer owes the
        down payment, the finance company owes the financed amount, and the
        whole price is held for the retailer until settlement."""
        self.ensure_one()
        marketplace = self.company_id.sudo()
        customer = self.partner_id.commercial_partner_id
        lender_partner = self.finance_company_id.company_id.partner_id
        vendor_partner = self.vendor_id.sudo().partner_id.commercial_partner_id
        lines = [
            (0, 0, {'name': f"{self.name} financed by {self.finance_company_id.name}",
                    'account_id': lender_partner.with_company(marketplace).property_account_receivable_id.id,
                    'partner_id': lender_partner.id, 'debit': self.financed_amount}),
            (0, 0, {'name': f"{self.name} {self.product_id.display_name} (held for {vendor_partner.name})",
                    'account_id': marketplace.emi_vendor_clearing_account_id.id,
                    'partner_id': vendor_partner.id, 'credit': self.list_price}),
        ]
        if self.down_payment_amount:
            lines.insert(0, (0, 0, {
                'name': f"{self.name} down payment",
                'account_id': customer.with_company(marketplace).property_account_receivable_id.id,
                'partner_id': customer.id, 'debit': self.down_payment_amount,
            }))
        move = self.env['account.move'].sudo().with_company(marketplace).create({
            'move_type': 'entry',
            'journal_id': marketplace.emi_journal_id.id,
            'date': date,
            'ref': f"{self.name} EMI sale",
            'emi_application_id': self.id,
            'line_ids': lines,
        })
        move.action_post()
        # A down payment received before disbursement sits as an outstanding
        # credit on the customer: match it now.
        receivable_lines = move.line_ids.filtered(lambda l: l.account_id.account_type == 'asset_receivable'
                                                  and l.partner_id == customer)
        if receivable_lines:
            outstanding = self.env['account.move.line'].sudo().search([
                ('company_id', '=', marketplace.id), ('partner_id', '=', customer.id),
                ('account_id', '=', receivable_lines.account_id.id), ('reconciled', '=', False),
                ('parent_state', '=', 'posted'), ('balance', '<', 0),
                ('move_id.emi_application_id', '=', self.id),
            ])
            if outstanding:
                (receivable_lines | outstanding).reconcile()
        return move

    def _emi_create_commission_invoice(self, date):
        self.ensure_one()
        marketplace = self.company_id.sudo()
        amount = self._emi_commission()
        if not amount:
            return self.env['account.move'], 0.0
        product = marketplace.emi_commission_product_id
        vendor_partner = self.vendor_id.sudo().partner_id.commercial_partner_id
        invoice = self.env['account.move'].sudo().with_company(marketplace).create({
            'move_type': 'out_invoice',
            'partner_id': vendor_partner.id,
            'invoice_date': date,
            'invoice_origin': self.name,
            'emi_application_id': self.id,
            'invoice_line_ids': [(0, 0, {
                'product_id': product.id,
                'name': f"Marketplace commission on {self.name} ({self.product_id.display_name})",
                'quantity': 1,
                'price_unit': amount,
                'tax_ids': [(6, 0, product.taxes_id.filtered(lambda t: t.company_id == marketplace).ids)],
            })],
        })
        invoice.action_post()
        return invoice, amount

    def action_disburse(self):
        """Post the lender's loan entry, the marketplace's collection entry and
        the commission invoice to the retailer, then build the installment
        schedule. Roles and configuration are checked before anything is
        written; the entries span two companies, so they are posted as
        superuser once the reviewer is known to be allowed."""
        self._check_group(REVIEWER)
        self._check_finance_company_member()
        for app in self:
            if app.state != 'approved':
                raise UserError("Only approved applications can be disbursed.")
            app.sudo()._emi_check_ready_to_disburse()
        res = super().action_disburse()
        date = fields.Date.context_today(self)
        for app in self.sudo():
            finance_move = app._emi_create_finance_move(date)
            marketplace_move = app._emi_create_marketplace_move(date)
            commission_invoice, commission = app._emi_create_commission_invoice(date)
            schedule = build_schedule(
                app.financed_amount, app.interest_rate_percent, app.tenure_months,
                app.interest_calc_method, date, round_fn=app.currency_id.round,
            )
            app.write({
                'disbursement_date': date,
                'finance_move_id': finance_move.id,
                'marketplace_move_id': marketplace_move.id,
                'commission_invoice_id': commission_invoice.id,
                'commission_amount': commission,
                'schedule_line_ids': [(0, 0, {
                    'number': line['number'], 'due_date': line['due_date'],
                    'opening_balance': line['opening_balance'], 'amount': line['amount'],
                    'principal_amount': line['principal_amount'], 'interest_amount': line['interest_amount'],
                    'closing_balance': line['closing_balance'],
                }) for line in schedule],
            })
        return res

    def action_close(self):
        for app in self:
            if app.schedule_line_ids.filtered(lambda l: l.state != 'paid'):
                raise UserError(f"{app.name} still has unpaid installments.")
        return super().action_close()

    # ------------------------------------------------------------------
    # Collections
    # ------------------------------------------------------------------

    def action_open_installment_payment(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Register Installment Payment',
            'res_model': 'emi.installment.payment',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_application_id': self.id},
        }

    def action_open_down_payment(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Register Down Payment',
            'res_model': 'emi.down.payment',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_application_id': self.id},
        }

    def action_view_journal_entries(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'EMI Journal Entries',
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': [('emi_application_id', '=', self.id)],
            'context': {'create': False},
        }


class AccountMove(models.Model):
    _inherit = 'account.move'

    emi_application_id = fields.Many2one('emi.application', string='EMI Application', index=True, copy=False,
                                         readonly=True)
