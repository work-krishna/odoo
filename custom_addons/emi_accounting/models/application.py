# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError
from odoo.tools import SQL

from odoo.addons.emi_accounting.tools.amortization import build_schedule, effective_monthly_rate
from odoo.addons.emi_application.models.application import OFFICER, REVIEWER, EmiApplication as BaseApplication

BILLING = 'account.group_account_invoice'
EMI_PAYMENT_KINDS = [
    ('down_payment', 'Down Payment'),
    ('installment', 'Installment'),
    ('unallocated', 'Unallocated'),
]


def _receivable_line(move, partner):
    return move.line_ids.filtered(
        lambda l: l.partner_id == partner and l.account_id.account_type == 'asset_receivable'
    )


def _check_collector(env, company, groups):
    """Only staff of the collecting company with an EMI or billing role."""
    if env.su:
        return
    if not any(env.user.has_group(g) for g in groups):
        raise AccessError("You are not allowed to register EMI payments.")
    if company not in env.user.company_ids:
        raise AccessError(f"Payments for this loan are collected by {company.name}, which you do not work for.")


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
        help="Installments not yet paid, including those not yet due, less what was paid in advance.",
    )
    advance_amount = fields.Monetary(
        string='Paid in Advance', compute='_compute_installment_summary',
        help="Installment payments received before the installments fell due. Each installment is "
             "settled from it when it is posted on its due date.",
    )
    next_due_date = fields.Date(compute='_compute_installment_summary')
    overdue_amount = fields.Monetary(compute='_compute_installment_summary')
    down_payment_received = fields.Monetary(
        compute='_compute_down_payment_received',
        help="Down payment receipts booked for this application, net of refunds.",
    )

    @api.depends('schedule_line_ids.state', 'schedule_line_ids.amount_residual')
    def _compute_installment_summary(self):
        for app in self:
            lines = app.schedule_line_ids
            open_lines = lines.filtered(lambda l: l.state not in ('paid', 'settled'))
            advance = app._emi_advance_amount()
            next_line, _amount = app._emi_next_installment(advance)
            app.advance_amount = advance
            app.installments_paid = len(lines.filtered(lambda l: l.state == 'paid'))
            app.amount_outstanding = app.currency_id.round(sum(open_lines.mapped('amount_residual')) - advance)
            app.next_due_date = next_line.due_date
            app.overdue_amount = sum(open_lines.filtered(lambda l: l.state == 'overdue').mapped('amount_residual'))

    def _compute_down_payment_received(self):
        for app in self:
            app.down_payment_received = app._emi_down_payment_received()

    def _emi_invalidate_summary(self):
        """The summary also depends on journal items, which the ORM does not track here."""
        self.invalidate_recordset([
            'installments_paid', 'amount_outstanding', 'advance_amount', 'next_due_date', 'overdue_amount',
            'down_payment_received',
        ])

    def _emi_lock(self):
        """Serialize money movements on these applications: a concurrent
        receipt conflicts on this row (and is retried) instead of passing the
        same 'what is still due' checks."""
        ids = tuple(self._origin.ids)
        if ids:
            self.env.cr.execute(SQL("UPDATE emi_application SET write_date = write_date WHERE id IN %s", ids))
        self._emi_invalidate_summary()

    @api.ondelete(at_uninstall=False)
    def _unlink_except_with_entries(self):
        if self.env['account.move'].sudo().search_count([('emi_application_id', 'in', self.ids)], limit=1):
            raise UserError("Applications with journal entries or payments cannot be deleted.")

    def write(self, vals):
        # Also for sudo writes (website): the receipts are booked against this customer and amount.
        if 'partner_id' in vals or 'down_payment_amount' in vals:
            for app in self:
                received = app._emi_down_payment_received()
                if not received:
                    continue
                if 'partner_id' in vals and vals['partner_id'] != app.partner_id.id:
                    raise UserError(f"{app.name} holds a down payment from {app.partner_id.name}; "
                                    "refund it before changing the customer.")
                if app.currency_id.compare_amounts(vals.get('down_payment_amount', received), received) < 0:
                    raise UserError(f"{app.currency_id.format(received)} of down payment was already received "
                                    f"for {app.name}; the down payment cannot be lower.")
        return super().write(vals)

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
                ('move_id.emi_application_id', '=', self.id), ('move_id.emi_payment_kind', '=', 'down_payment'),
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
            if app.schedule_line_ids.filtered(lambda l: l.state not in ('paid', 'settled')):
                raise UserError(f"{app.name} still has unpaid installments.")
        return super().action_close()

    def action_emi_cancel_disbursement(self):
        """Undo a disbursement booked by mistake: reverse the loan, collection
        and installment entries, credit the commission invoice and put the
        application back to approved, without a schedule. Receipts are not
        touched: a down payment goes back to waiting for the next disbursement."""
        self._check_group(REVIEWER)
        self._check_finance_company_member()
        date = fields.Date.context_today(self)
        for app in self.sudo():
            if app.state not in ('disbursed', 'active'):
                raise UserError("Only disbursed loans can have their disbursement cancelled.")
            app._emi_lock()
            if self.env['account.move'].sudo().search_count([
                ('emi_application_id', '=', app.id), ('emi_payment_kind', '=', 'installment'),
                ('state', '=', 'posted'),
            ], limit=1):
                raise UserError(f"{app.name} has installment payments: reverse them first "
                                "(Reverse EMI Receipt on each payment).")
            clearing = app.marketplace_move_id.line_ids.filtered(
                lambda l: l.account_id == app.company_id.emi_vendor_clearing_account_id)
            if clearing.matched_debit_ids or clearing.matched_credit_ids:
                raise UserError(f"The sale of {app.name} is already settled with the retailer: "
                                "reverse that settlement first.")
            invoice = app.commission_invoice_id
            if invoice and invoice.payment_state != 'not_paid':
                raise UserError(f"The commission invoice {invoice.name} is already paid: "
                                "unreconcile its payment first.")
            moves = (app.finance_move_id | app.marketplace_move_id | app.schedule_line_ids.due_move_id).filtered(
                lambda m: m.state == 'posted')
            moves.with_context(emi_reversal=True)._reverse_moves([{
                'date': date, 'ref': f"Reversal of {move.ref or move.name}", 'emi_application_id': app.id,
            } for move in moves], cancel=True)
            if invoice.state == 'posted':
                invoice.with_context(emi_reversal=True)._reverse_moves([{
                    'date': date, 'invoice_date': date, 'emi_application_id': app.id,
                    'ref': f"Cancelled disbursement of {app.name}",
                }], cancel=True)
            app.schedule_line_ids.unlink()
            app.write({
                'state': 'approved', 'disbursement_date': False, 'finance_move_id': False,
                'marketplace_move_id': False, 'commission_invoice_id': False, 'commission_amount': 0.0,
            })
            app._emi_invalidate_summary()
            app.message_post(body=f"Disbursement cancelled by {self.env.user.name}: the loan, collection and "
                                  "installment entries were reversed and the commission invoice credited. "
                                  "Payments matched with them (down payment, financing) are open again.")
        return True

    # ------------------------------------------------------------------
    # Early settlement
    # ------------------------------------------------------------------

    def _emi_foreclosure_quote(self, date):
        """Early settlement as of ``date``: the principal not billed yet plus
        the interest accrued on it since the last due date (or disbursement),
        pro rata by days of that period, at the loan's effective monthly rate.
        Installments due by ``date`` stay billed and are collected as usual."""
        self.ensure_one()
        app = self.sudo()
        lines = app.schedule_line_ids.sorted('number')
        if lines.filtered('is_foreclosure'):
            raise UserError(f"{app.name} is already settled early.")
        billed = lines.filtered(lambda l: l.due_move_id or l.due_date <= date)
        unbilled = lines - billed
        if not unbilled:
            raise UserError(f"Every installment of {app.name} is already due: collect the outstanding balance.")
        principal = app.currency_id.round(sum(unbilled.mapped('principal_amount')))
        start = max(billed.mapped('due_date'), default=app.disbursement_date)
        period = max((unbilled[0].due_date - start).days, 1)
        days = min(max((date - start).days, 0), period)
        rate = effective_monthly_rate(
            app.financed_amount, app.interest_rate_percent, app.tenure_months, app.interest_calc_method,
        )
        interest = app.currency_id.round(principal * rate * days / period)
        return {
            'billed': billed, 'unbilled': unbilled,
            'principal': principal, 'interest': interest, 'amount': app.currency_id.round(principal + interest),
        }

    def action_emi_foreclose(self, date=None):
        """Settle the loan early: bill the payoff as one last installment and
        mark the installments it replaces as settled early. The customer then
        pays it like any installment (wizard or portal)."""
        self._check_group(REVIEWER)
        self._check_finance_company_member()
        date = date or fields.Date.context_today(self)
        for app in self.sudo():
            if app.state not in ('disbursed', 'active'):
                raise UserError("Only disbursed loans can be settled early.")
            app._emi_lock()
            quote = app._emi_foreclosure_quote(date)
            quote['billed']._post_installment_entry()  # those due by now and not posted yet
            quote['unbilled'].write({'settled_early': True})
            payoff = self.env['emi.schedule.line'].sudo().create({
                'application_id': app.id, 'number': max(app.schedule_line_ids.mapped('number')) + 1,
                'due_date': date, 'opening_balance': quote['principal'], 'amount': quote['amount'],
                'principal_amount': quote['principal'], 'interest_amount': quote['interest'],
                'closing_balance': 0.0, 'is_foreclosure': True,
            })
            payoff._post_installment_entry(date=date)
            app.message_post(body=(
                f"Settled early by {self.env.user.name}: payoff {app.currency_id.format(quote['amount'])} "
                f"(principal {app.currency_id.format(quote['principal'])}, accrued interest "
                f"{app.currency_id.format(quote['interest'])}) replaces {len(quote['unbilled'])} installments."
            ))
        return True

    def action_open_foreclosure(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Early Settlement',
            'res_model': 'emi.foreclosure',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_application_id': self.id},
        }

    # ------------------------------------------------------------------
    # Collections
    # ------------------------------------------------------------------

    def _emi_payment_company(self, kind):
        """Company whose bank or gateway receives this kind of payment."""
        self.ensure_one()
        if kind == 'down_payment' or self.finance_company_id.installment_collection == 'marketplace':
            return self.company_id
        return self.finance_company_id.company_id

    def _emi_down_payment_received(self):
        """Down payment receipts (net of refunds) booked in the marketplace for this application."""
        self.ensure_one()
        app = self.sudo()
        if not app._origin.id:
            return 0.0
        lines = self.env['account.move.line'].sudo().search([
            ('move_id.emi_application_id', '=', app._origin.id), ('move_id.emi_payment_kind', '=', 'down_payment'),
            ('company_id', '=', app.company_id.id), ('partner_id', '=', app.partner_id.commercial_partner_id.id),
            ('account_id.account_type', '=', 'asset_receivable'), ('parent_state', '=', 'posted'),
        ])
        return app.currency_id.round(-sum(lines.mapped('balance')))

    def _emi_open_advance_lines(self):
        """Installment receipts in the lender's books not yet matched with a
        posted installment: the customer's advance on this loan."""
        self.ensure_one()
        app = self.sudo()
        if not app._origin.id or not app.schedule_line_ids:
            return self.env['account.move.line']
        return self.env['account.move.line'].sudo().search([
            ('company_id', '=', app.finance_company_id.company_id.id),
            ('partner_id', '=', app.partner_id.commercial_partner_id.id),
            ('account_id.account_type', '=', 'asset_receivable'), ('parent_state', '=', 'posted'),
            ('reconciled', '=', False), ('balance', '<', 0),
            ('move_id.emi_application_id', '=', app._origin.id), ('move_id.emi_payment_kind', '=', 'installment'),
        ])

    def _emi_advance_amount(self):
        self.ensure_one()
        return self.currency_id.round(-sum(self._emi_open_advance_lines().mapped('amount_residual')))

    def _emi_next_installment(self, advance=None):
        """(schedule line, amount) the customer is asked to pay next, once the
        advance is set against the open installments in order."""
        self.ensure_one()
        currency = self.currency_id
        advance = self._emi_advance_amount() if advance is None else advance
        for line in self.schedule_line_ids.filtered(lambda l: l.state not in ('paid', 'settled')).sorted('number'):
            covered = min(advance, line.amount_residual)
            advance -= covered
            if currency.compare_amounts(line.amount_residual - covered, 0.0) > 0:
                return line, currency.round(line.amount_residual - covered)
        return self.env['emi.schedule.line'], 0.0

    def _emi_amount_due(self, kind):
        """What the customer can pay now: the unpaid down payment, or the next installment."""
        self.ensure_one()
        app = self.sudo()
        if kind == 'down_payment':
            if app.state in ('draft', 'rejected', 'closed', 'defaulted'):
                return 0.0
            if app.marketplace_move_id:
                # Disbursed: whatever the collection entry still expects from the customer.
                due = sum(_receivable_line(
                    app.marketplace_move_id, app.partner_id.commercial_partner_id).mapped('amount_residual'))
            else:
                due = app.down_payment_amount - app._emi_down_payment_received()
            return max(app.currency_id.round(due), 0.0)
        if app.state not in ('disbursed', 'active'):
            return 0.0
        return app._emi_next_installment()[1]

    def _emi_register_down_payment(self, amount, date, journal):
        """Book a down payment received by the marketplace; returns the account.payment."""
        self.ensure_one()
        app = self.sudo()
        if app.state in ('draft', 'rejected', 'closed', 'defaulted'):
            raise UserError("Down payments are taken on submitted applications until disbursement.")
        if not amount or amount <= 0:
            raise UserError("The down payment must be positive.")
        app._emi_lock()
        due = app._emi_amount_due('down_payment')
        if app.currency_id.compare_amounts(amount, due) > 0:
            raise UserError(f"Only {app.currency_id.format(due)} of the down payment is still due on {app.name}.")
        marketplace = app.company_id.sudo()
        customer = app.partner_id.commercial_partner_id
        payment = app._emi_create_payment(
            marketplace, customer, amount, date, journal, f"{app.name} down payment", 'down_payment',
        )
        if app.marketplace_move_id:
            (app.marketplace_move_id | payment.move_id).line_ids.filtered(
                lambda l: l.partner_id == customer and l.account_id.account_type == 'asset_receivable'
                and not l.reconciled
            ).reconcile()
        app._emi_invalidate_summary()
        return payment

    def _emi_refund_down_payment(self, amount, date, journal):
        """Pay back the down payment of a rejected application; returns the outbound account.payment."""
        self.ensure_one()
        app = self.sudo()
        if app.state != 'rejected':
            raise UserError("Down payments are refunded on rejected applications.")
        if not amount or amount <= 0:
            raise UserError("The refund must be positive.")
        app._emi_lock()
        received = app._emi_down_payment_received()
        if app.currency_id.compare_amounts(amount, received) > 0:
            raise UserError(f"Only {app.currency_id.format(received)} of down payment is held for {app.name}.")
        customer = app.partner_id.commercial_partner_id
        refund = app._emi_create_payment(
            app.company_id.sudo(), customer, amount, date, journal, f"{app.name} down payment refund",
            'down_payment', payment_type='outbound',
        )
        self.env['account.move.line'].sudo().search([
            ('move_id.emi_application_id', '=', app.id), ('move_id.emi_payment_kind', '=', 'down_payment'),
            ('company_id', '=', app.company_id.id), ('partner_id', '=', customer.id),
            ('account_id', '=', _receivable_line(refund.move_id, customer).account_id.id),
            ('parent_state', '=', 'posted'), ('reconciled', '=', False),
        ]).reconcile()
        app._emi_invalidate_summary()
        app.message_post(body=f"Down payment refund of {app.currency_id.format(amount)} booked ({refund.name}).")
        return refund

    def _emi_register_installment_payment(self, amount, date, journal, memo=None):
        """Book an installment payment and reconcile it with the posted
        installments, oldest first. What they cannot take stays on the
        customer's account in the lender's books as an advance, applied to the
        next installments when they are posted on their due date. Returns the
        customer's account.payment."""
        self.ensure_one()
        app = self.sudo()
        if app.state not in ('disbursed', 'active'):
            raise UserError("Installments can only be paid on disbursed or active loans.")
        if not amount or amount <= 0:
            raise UserError("The payment amount must be positive.")
        app._emi_lock()
        if app.currency_id.compare_amounts(amount, app.amount_outstanding) > 0:
            raise UserError("The payment is larger than the loan's outstanding balance.")

        memo = memo or f"{app.name} installment"
        customer = app.partner_id.commercial_partner_id
        lender = app.finance_company_id.company_id.sudo()
        if app.finance_company_id.installment_collection == 'marketplace':
            marketplace = app.company_id.sudo()
            payment = app._emi_create_payment(marketplace, customer, amount, date, journal, memo, 'installment')
            lender_partner = lender.partner_id
            # Marketplace: the receipt is owed to the lender, not revenue.
            reclass = app._emi_post_entry(marketplace, date, memo, [
                (customer, customer.with_company(marketplace).property_account_receivable_id, amount),
                (lender_partner, lender_partner.with_company(marketplace).property_account_payable_id, -amount),
            ], receipt=payment)
            (_receivable_line(payment.move_id, customer) | _receivable_line(reclass, customer)).reconcile()
            # Lender: the customer's installments are settled by the marketplace.
            marketplace_partner = marketplace.partner_id
            app._emi_post_entry(lender, date, memo, [
                (marketplace_partner, marketplace_partner.with_company(lender).property_account_receivable_id,
                 amount),
                (customer, customer.with_company(lender).property_account_receivable_id, -amount),
            ], kind='installment', receipt=payment)
        else:
            payment = app._emi_create_payment(lender, customer, amount, date, journal, memo, 'installment')
        app._emi_apply_advances()
        if app.state == 'disbursed':
            app.write({'state': 'active'})
        return payment

    def _emi_apply_advances(self):
        """Match the posted, unpaid installments with the loan's open installment receipts."""
        for app in self.sudo():
            due_lines = app.schedule_line_ids.due_move_line_id.filtered(
                lambda l: l.parent_state == 'posted' and not l.reconciled)
            advances = app._emi_open_advance_lines() if due_lines else due_lines
            for account in advances.account_id:
                lines = (due_lines | advances).filtered(lambda l: l.account_id == account)
                if lines.filtered(lambda l: l.balance > 0):
                    lines.reconcile()
        self._emi_invalidate_summary()

    def _emi_create_payment(self, company, customer, amount, date, journal, memo, kind, payment_type='inbound'):
        journal = journal.sudo()
        if journal.company_id != company:
            raise UserError(f"Use a bank or cash journal of {company.name} for this payment.")
        if journal.currency_id and journal.currency_id != self.currency_id:
            raise UserError(f"{journal.name} is in {journal.currency_id.name}; "
                            f"payments on {self.name} are in {self.currency_id.name}.")
        payment = self.env['account.payment'].sudo().with_company(company).create({
            'payment_type': payment_type,
            'partner_type': 'customer',
            'partner_id': customer.id,
            'amount': amount,
            'currency_id': self.currency_id.id,
            'date': date,
            'journal_id': journal.id,
            'memo': memo,
        })
        payment.action_post()
        if not payment.move_id:
            raise UserError(f"{journal.name} records payments without a journal entry; set an outstanding "
                            "account on its payment methods to take EMI payments.")
        payment.move_id.write({'emi_application_id': self.id, 'emi_payment_kind': kind})
        return payment

    def _emi_post_entry(self, company, date, memo, lines, kind=False, receipt=None):
        move = self.env['account.move'].sudo().with_company(company).create({
            'move_type': 'entry',
            'journal_id': company.emi_journal_id.id,
            'date': date,
            'ref': memo,
            'emi_application_id': self.id,
            'emi_payment_kind': kind,
            'emi_receipt_id': receipt.id if receipt else False,
            'line_ids': [(0, 0, {
                'name': memo, 'partner_id': partner.id, 'account_id': account.id,
                'debit': amount if amount > 0 else 0.0, 'credit': -amount if amount < 0 else 0.0,
            }) for partner, account, amount in lines],
        })
        move.action_post()
        return move

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

    def action_open_down_payment_refund(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Refund Down Payment',
            'res_model': 'emi.down.payment.refund',
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
    emi_payment_kind = fields.Selection(
        EMI_PAYMENT_KINDS, string='EMI Receipt', readonly=True, copy=False,
        help="What an EMI customer receipt pays; also set on the lender's entry settling an "
             "installment the marketplace collected.",
    )
    emi_receipt_id = fields.Many2one(
        'account.payment', string='Booked for EMI Receipt', readonly=True, copy=False, index='btree_not_null',
        help="The customer payment this entry was booked for; it is cancelled together with it.",
    )

    def _emi_check_editable(self):
        """EMI entries are undone through the EMI actions only, which also
        keep the applications, schedules and settlements consistent."""
        if self.env.su and self.env.context.get('emi_reversal'):
            return
        moves = self.sudo()
        protected = moves.filtered('emi_application_id')
        protected |= self.env['emi.vendor.settlement'].sudo().search([('move_id', 'in', moves.ids)]).move_id
        if protected:
            raise UserError(
                f"{', '.join(protected.mapped('display_name'))}: EMI loan and retailer settlement entries "
                "cannot be reset, cancelled or reversed directly. Use Cancel Disbursement on the application, "
                "Reverse EMI Receipt on the payment, or Reverse on the retailer settlement."
            )

    def button_draft(self):
        self._emi_check_editable()
        return super().button_draft()

    def button_cancel(self):
        self._emi_check_editable()
        return super().button_cancel()

    def _reverse_moves(self, default_values_list=None, cancel=False):
        self._emi_check_editable()
        return super()._reverse_moves(default_values_list=default_values_list, cancel=cancel)


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    emi_application_id = fields.Many2one(related='move_id.emi_application_id', string='EMI Application')
    is_emi_receipt = fields.Boolean(compute='_compute_is_emi_receipt')

    def _compute_is_emi_receipt(self):
        for payment in self:
            payment.is_emi_receipt = bool(payment.sudo().move_id.emi_application_id)

    def action_emi_reverse(self):
        """Cancel EMI receipts (bounced cheque, wrong entry) together with the
        entries booked for them, so what they paid is due again."""
        for payment in self.sudo():
            app = payment.emi_application_id
            if not app:
                raise UserError(f"{payment.name} is not an EMI receipt.")
            # EMI staff register receipts without accounting rights: same check as the wizards.
            _check_collector(self.env, payment.company_id, (OFFICER, REVIEWER, BILLING))
            if payment.state == 'canceled':
                raise UserError(f"{payment.name} is already cancelled.")
            app._emi_lock()
            linked = self.env['account.move'].sudo().search([
                ('emi_receipt_id', '=', payment.id), ('state', '=', 'posted'),
            ])
            payment.with_context(emi_reversal=True).action_cancel()
            linked.with_context(emi_reversal=True).button_cancel()
            app._emi_invalidate_summary()
            app.message_post(body=f"Receipt {payment.name} ({app.currency_id.format(payment.amount)}) "
                                  f"reversed by {self.env.user.name}.")
        return True
