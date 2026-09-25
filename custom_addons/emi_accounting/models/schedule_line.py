# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import UserError


class EmiScheduleLine(models.Model):
    """One monthly installment of a disbursed EMI loan.

    On its due date the finance company posts the installment: the
    customer receivable is debited for the installment and loan principal
    and interest income are credited. Payments reconcile against that
    receivable line, which drives the paid/overdue status.
    """
    _name = 'emi.schedule.line'
    _description = 'EMI Installment'
    _order = 'application_id, number'

    application_id = fields.Many2one('emi.application', required=True, ondelete='cascade', index=True)
    finance_company_id = fields.Many2one(related='application_id.finance_company_id', store=True)
    partner_id = fields.Many2one(related='application_id.partner_id', store=True)
    currency_id = fields.Many2one(related='application_id.currency_id')
    number = fields.Integer(string='#', required=True)
    due_date = fields.Date(required=True, index=True)
    opening_balance = fields.Monetary(readonly=True)
    amount = fields.Monetary(string='Installment', required=True)
    principal_amount = fields.Monetary(string='Principal', required=True)
    interest_amount = fields.Monetary(string='Interest', required=True)
    closing_balance = fields.Monetary(readonly=True)

    due_move_id = fields.Many2one('account.move', string='Installment Entry', readonly=True, copy=False)
    due_move_line_id = fields.Many2one('account.move.line', readonly=True, copy=False,
                                       help="Customer receivable line the payments reconcile with.")
    amount_residual = fields.Monetary(string='Outstanding', compute='_compute_payment_state', store=True)
    state = fields.Selection(
        [('upcoming', 'Upcoming'), ('due', 'Due'), ('overdue', 'Overdue'), ('partial', 'Partially Paid'),
         ('paid', 'Paid'), ('settled', 'Settled Early')],
        compute='_compute_payment_state', store=True,
    )
    settled_early = fields.Boolean(readonly=True, copy=False,
                                   help="Replaced by the early settlement payoff; never billed.")
    is_foreclosure = fields.Boolean(string='Early Settlement', readonly=True, copy=False,
                                    help="The payoff billed when the loan was settled early.")

    _application_number_uniq = models.Constraint(
        'unique(application_id, number)',
        'Installment numbers are unique per application.',
    )

    @api.depends('due_date', 'amount', 'settled_early', 'due_move_id', 'due_move_line_id.amount_residual',
                 'due_move_line_id.reconciled')
    def _compute_payment_state(self):
        today = fields.Date.context_today(self)
        for line in self:
            if line.settled_early:
                line.amount_residual = 0.0
                line.state = 'settled'
                continue
            if line.due_move_line_id:
                residual = line.due_move_line_id.amount_residual
            else:
                residual = line.amount
            line.amount_residual = residual
            if line.currency_id and line.currency_id.is_zero(residual):
                line.state = 'paid'
            elif line.due_date < today:
                line.state = 'overdue'  # also when partly paid: it is still late
            elif residual < line.amount:
                line.state = 'partial'
            elif not line.due_move_id and line.due_date > today:
                line.state = 'upcoming'
            else:
                line.state = 'due'

    @api.model
    def _cron_refresh_overdue(self):
        """Stored state depends on today's date: refresh open lines daily."""
        open_lines = self.sudo().search([('state', 'in', ('upcoming', 'due', 'partial'))])
        open_lines._compute_payment_state()

    # ------------------------------------------------------------------
    # Posting
    # ------------------------------------------------------------------

    def _post_installment_entry(self, date=None):
        """Post the finance company's installment entry for these lines and
        settle it from any advance the customer paid on the loan."""
        to_post = self.filtered(
            lambda l: not l.settled_early and (not l.due_move_id or l.due_move_id.state == 'cancel'))
        for line in to_post.sorted('number'):
            app = line.application_id.sudo()
            company = app.finance_company_id.company_id.sudo()
            company._emi_check_accounting('finance')
            partner = app.partner_id.commercial_partner_id
            receivable = partner.with_company(company).property_account_receivable_id
            label = 'early settlement' if line.is_foreclosure else f"installment {line.number}"
            move = self.env['account.move'].sudo().with_company(company).create({
                'move_type': 'entry',
                'journal_id': company.emi_journal_id.id,
                'date': date or line.due_date,
                'ref': f"{app.name} {label}" + ('' if line.is_foreclosure else f"/{app.tenure_months}"),
                'emi_application_id': app.id,
                'line_ids': [
                    (0, 0, {'name': f"{app.name} {label}", 'account_id': receivable.id,
                            'partner_id': partner.id, 'debit': line.amount, 'date_maturity': line.due_date}),
                    (0, 0, {'name': f"{app.name} principal", 'account_id': company.emi_loan_account_id.id,
                            'partner_id': partner.id, 'credit': line.principal_amount}),
                ] + ([
                    (0, 0, {'name': f"{app.name} interest", 'account_id': company.emi_interest_income_account_id.id,
                            'partner_id': partner.id, 'credit': line.interest_amount}),
                ] if line.interest_amount else []),
            })
            move.action_post()
            line.sudo().write({
                'due_move_id': move.id,
                'due_move_line_id': move.line_ids.filtered(lambda l: l.account_id == receivable).id,
            })
        to_post.application_id._emi_apply_advances()

    @api.model
    def _cron_post_due_installments(self):
        lines = self.sudo().search([
            '|', ('due_move_id', '=', False), ('due_move_id.state', '=', 'cancel'),
            ('settled_early', '=', False),
            ('due_date', '<=', fields.Date.context_today(self)),
            ('application_id.state', 'in', ('disbursed', 'active')),
        ])
        lines._post_installment_entry()

    def action_register_payment(self):
        apps = self.application_id
        if len(apps) != 1:
            raise UserError("Register payments for one application at a time.")
        return apps.action_open_installment_payment()
