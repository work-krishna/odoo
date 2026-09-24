# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError

OFFICER = 'emi_finance.group_emi_officer'
REVIEWER = 'emi_finance.group_emi_finance_reviewer'
BILLING = 'account.group_account_invoice'


def _check_collector(env, company, groups):
    """Only staff of the collecting company with an EMI or billing role."""
    if env.su:
        return
    if not any(env.user.has_group(g) for g in groups):
        raise AccessError("You are not allowed to register EMI payments.")
    if company not in env.user.company_ids:
        raise AccessError(f"Payments for this loan are collected by {company.name}, which you do not work for.")


class EmiInstallmentPayment(models.TransientModel):
    _name = 'emi.installment.payment'
    _description = 'Register EMI Installment Payment'

    application_id = fields.Many2one('emi.application', required=True, ondelete='cascade')
    collecting_company_id = fields.Many2one('res.company', compute='_compute_collecting_company')
    currency_id = fields.Many2one(related='application_id.currency_id')
    # Not required: stored computes run after the INSERT; action_confirm validates it.
    amount = fields.Monetary(compute='_compute_amount', store=True, readonly=False)
    payment_date = fields.Date(required=True, default=fields.Date.context_today)
    journal_id = fields.Many2one(
        'account.journal', required=True,
        domain="[('type', 'in', ('bank', 'cash')), ('company_id', '=', collecting_company_id)]",
    )
    memo = fields.Char()

    @api.depends('application_id')
    def _compute_collecting_company(self):
        for wiz in self:
            app = wiz.application_id.sudo()
            if app.finance_company_id.installment_collection == 'marketplace':
                wiz.collecting_company_id = app.company_id
            else:
                wiz.collecting_company_id = app.finance_company_id.company_id

    @api.depends('application_id')
    def _compute_amount(self):
        for wiz in self:
            open_lines = wiz.application_id.sudo().schedule_line_ids.filtered(lambda l: l.state != 'paid')
            wiz.amount = open_lines[:1].amount_residual

    def action_confirm(self):
        self.ensure_one()
        app = self.application_id.sudo()
        _check_collector(self.env, self.collecting_company_id, (OFFICER, REVIEWER, BILLING))
        if app.state not in ('disbursed', 'active'):
            raise UserError("Installments can only be paid on disbursed or active loans.")
        if not self.amount or self.amount <= 0:
            raise UserError("The payment amount must be positive.")
        open_lines = app.schedule_line_ids.filtered(lambda l: l.state != 'paid').sorted('number')
        if self.currency_id.compare_amounts(self.amount, sum(open_lines.mapped('amount_residual'))) > 0:
            raise UserError("The payment is larger than the loan's outstanding balance.")

        # Make sure every installment the payment reaches has its entry.
        remaining, to_cover = self.amount, self.env['emi.schedule.line']
        for line in open_lines:
            if remaining <= 0:
                break
            to_cover |= line
            remaining -= line.amount_residual
        for line in to_cover.filtered(lambda l: not l.due_move_id):
            line._post_installment_entry(date=min(line.due_date, self.payment_date))
        due_lines = to_cover.due_move_line_id

        memo = self.memo or f"{app.name} installment"
        customer = app.partner_id.commercial_partner_id
        lender = app.finance_company_id.company_id.sudo()
        if app.finance_company_id.installment_collection == 'marketplace':
            marketplace = app.company_id.sudo()
            payment = self._create_payment(marketplace, customer, memo)
            payment_line = self._receivable_line(payment.move_id, customer)
            lender_partner = lender.partner_id
            # Marketplace: the receipt is owed to the lender, not revenue.
            reclass = self._post_entry(marketplace, memo, [
                (customer, customer.with_company(marketplace).property_account_receivable_id, self.amount),
                (lender_partner, lender_partner.with_company(marketplace).property_account_payable_id, -self.amount),
            ])
            (payment_line | self._receivable_line(reclass, customer)).reconcile()
            # Lender: the customer's installment is settled by the marketplace.
            marketplace_partner = marketplace.partner_id
            settle = self._post_entry(lender, memo, [
                (marketplace_partner, marketplace_partner.with_company(lender).property_account_receivable_id,
                 self.amount),
                (customer, customer.with_company(lender).property_account_receivable_id, -self.amount),
            ])
            (self._receivable_line(settle, customer) | due_lines).reconcile()
        else:
            payment = self._create_payment(lender, customer, memo)
            (self._receivable_line(payment.move_id, customer) | due_lines).reconcile()
        if app.state == 'disbursed':
            app.sudo().write({'state': 'active'})
        return {'type': 'ir.actions.act_window_close'}

    def _create_payment(self, company, customer, memo):
        payment = self.env['account.payment'].sudo().with_company(company).create({
            'payment_type': 'inbound',
            'partner_type': 'customer',
            'partner_id': customer.id,
            'amount': self.amount,
            'date': self.payment_date,
            'journal_id': self.journal_id.id,
            'memo': memo,
        })
        payment.action_post()
        payment.move_id.emi_application_id = self.application_id.id
        return payment

    def _post_entry(self, company, memo, lines):
        move = self.env['account.move'].sudo().with_company(company).create({
            'move_type': 'entry',
            'journal_id': company.emi_journal_id.id,
            'date': self.payment_date,
            'ref': memo,
            'emi_application_id': self.application_id.id,
            'line_ids': [(0, 0, {
                'name': memo, 'partner_id': partner.id, 'account_id': account.id,
                'debit': amount if amount > 0 else 0.0, 'credit': -amount if amount < 0 else 0.0,
            }) for partner, account, amount in lines],
        })
        move.action_post()
        return move

    @staticmethod
    def _receivable_line(move, partner):
        return move.line_ids.filtered(
            lambda l: l.partner_id == partner and l.account_id.account_type == 'asset_receivable'
        )


class EmiDownPayment(models.TransientModel):
    _name = 'emi.down.payment'
    _description = 'Register EMI Down Payment'

    application_id = fields.Many2one('emi.application', required=True, ondelete='cascade')
    company_id = fields.Many2one(related='application_id.company_id')
    currency_id = fields.Many2one(related='application_id.currency_id')
    amount = fields.Monetary(compute='_compute_amount', store=True, readonly=False)
    payment_date = fields.Date(required=True, default=fields.Date.context_today)
    journal_id = fields.Many2one(
        'account.journal', required=True,
        domain="[('type', 'in', ('bank', 'cash')), ('company_id', '=', company_id)]",
    )

    @api.depends('application_id')
    def _compute_amount(self):
        for wiz in self:
            wiz.amount = wiz.application_id.down_payment_amount

    def action_confirm(self):
        self.ensure_one()
        app = self.application_id.sudo()
        marketplace = app.company_id.sudo()
        _check_collector(self.env, marketplace, (OFFICER, BILLING))
        if app.state in ('draft', 'rejected', 'closed', 'defaulted'):
            raise UserError("Down payments are taken on submitted applications until disbursement.")
        if not self.amount or self.amount <= 0:
            raise UserError("The down payment must be positive.")
        customer = app.partner_id.commercial_partner_id
        payment = self.env['account.payment'].sudo().with_company(marketplace).create({
            'payment_type': 'inbound',
            'partner_type': 'customer',
            'partner_id': customer.id,
            'amount': self.amount,
            'date': self.payment_date,
            'journal_id': self.journal_id.id,
            'memo': f"{app.name} down payment",
        })
        payment.action_post()
        payment.move_id.emi_application_id = app.id
        if app.marketplace_move_id:
            lines = (app.marketplace_move_id | payment.move_id).line_ids.filtered(
                lambda l: l.partner_id == customer and l.account_id.account_type == 'asset_receivable'
                and not l.reconciled
            )
            lines.reconcile()
        return {'type': 'ir.actions.act_window_close'}
