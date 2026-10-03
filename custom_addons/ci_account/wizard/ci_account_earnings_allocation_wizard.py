# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import Command, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import format_date

from ..models.ci_account_report import FISCAL_YEAR_RESET_TYPES


class CiAccountEarningsAllocationWizard(models.TransientModel):
    """Year-end closing: move the unallocated earnings (profit or loss not yet
    allocated, up to the closing date) from the current year earnings account
    to a retained earnings account. Income and expense accounts keep their
    balances; reports reset them at each fiscal year."""
    _name = 'ci.account.earnings.allocation.wizard'
    _description = "Year-End Earnings Allocation"

    company_id = fields.Many2one('res.company', required=True, readonly=True, default=lambda self: self.env.company)
    currency_id = fields.Many2one(related='company_id.currency_id')
    date = fields.Date(string="Closing Date", required=True, default=lambda self: self._default_date(),
                       help="Last day of the fiscal year to close; the entry is dated on it.")
    journal_id = fields.Many2one(
        'account.journal', required=True, check_company=True,
        domain="[('type', '=', 'general'), ('company_id', '=', company_id)]",
        default=lambda self: self.env['account.journal'].search(
            [('type', '=', 'general'), ('company_id', '=', self.env.company.id)], limit=1))
    unaffected_account_id = fields.Many2one(
        'account.account', string="Current Year Earnings Account", required=True,
        domain="[('account_type', '=', 'equity_unaffected')]",
        default=lambda self: self.env['account.account'].search([
            ('company_ids', 'in', self.env.company.id), ('account_type', '=', 'equity_unaffected')], limit=1))
    retained_earnings_account_id = fields.Many2one(
        'account.account', string="Retained Earnings Account", required=True,
        domain="[('account_type', '=', 'equity')]",
        default=lambda self: self.env.company.ci_retained_earnings_account_id)
    amount = fields.Monetary(
        string="Unallocated Earnings", compute='_compute_amount', currency_field='currency_id',
        help="Profit (positive) or loss (negative) not allocated yet up to the closing date.")

    def _default_date(self):
        company = self.env.company
        current = company.compute_fiscalyear_dates(fields.Date.context_today(self))
        return current['date_from'] - timedelta(days=1)

    @api.depends('company_id', 'date')
    def _compute_amount(self):
        for wizard in self:
            if not wizard.date:
                wizard.amount = 0.0
                continue
            groups = self.env['account.move.line']._read_group([
                ('company_id', '=', wizard.company_id.id),
                ('parent_state', '=', 'posted'),
                ('date', '<=', wizard.date),
                ('account_id.account_type', 'in', FISCAL_YEAR_RESET_TYPES),
            ], [], ['balance:sum'])
            wizard.amount = -(groups[0][0] or 0.0)

    def action_allocate(self):
        self.ensure_one()
        _ = self.env._
        if self.currency_id.is_zero(self.amount):
            raise UserError(_("There are no unallocated earnings up to %s.", format_date(self.env, self.date)))
        label = _("Allocation of the earnings up to %s", format_date(self.env, self.date))
        move = self.env['account.move'].create({
            'move_type': 'entry',
            'company_id': self.company_id.id,
            'journal_id': self.journal_id.id,
            'date': self.date,
            'ref': label,
            'line_ids': [
                Command.create({'name': label, 'account_id': self.unaffected_account_id.id, 'balance': self.amount}),
                Command.create({'name': label, 'account_id': self.retained_earnings_account_id.id,
                                'balance': -self.amount}),
            ],
        })
        move.action_post()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'res_id': move.id,
            'views': [(False, 'form')],
        }
