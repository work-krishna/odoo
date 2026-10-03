# -*- coding: utf-8 -*-
from collections import defaultdict

from dateutil.relativedelta import relativedelta

from odoo import Command, api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Domain
from odoo.tools import date_utils, format_date


class CiAccountTaxClosingWizard(models.TransientModel):
    """Tax return closing entry: empties the tax accounts of the period into
    the payable (tax due) or receivable (tax to recover) account of each tax
    group, then optionally sets the tax lock date to the end of the period."""
    _name = 'ci.account.tax.closing.wizard'
    _description = "Tax Return Closing"

    company_id = fields.Many2one('res.company', required=True, readonly=True, default=lambda self: self.env.company)
    currency_id = fields.Many2one(related='company_id.currency_id')
    date_from = fields.Date(required=True, default=lambda self: self._default_period()[0])
    date_to = fields.Date(required=True, default=lambda self: self._default_period()[1])
    journal_id = fields.Many2one(
        'account.journal', required=True, check_company=True,
        domain="[('type', '=', 'general'), ('company_id', '=', company_id)]",
        default=lambda self: self.env['account.journal'].search(
            [('type', '=', 'general'), ('company_id', '=', self.env.company.id)], limit=1))
    payable_account_id = fields.Many2one(
        'account.account', string="Default Payable Account",
        default=lambda self: self.env.company.ci_tax_payable_account_id,
        help="Used for the tax groups without a tax payable account.")
    receivable_account_id = fields.Many2one(
        'account.account', string="Default Receivable Account",
        default=lambda self: self.env.company.ci_tax_receivable_account_id,
        help="Used for the tax groups without a tax receivable account.")
    set_tax_lock_date = fields.Boolean(string="Lock the period", default=True,
                                       help="Set the tax return lock date to the end of the period.")
    line_ids = fields.One2many('ci.account.tax.closing.wizard.line', 'wizard_id', compute='_compute_line_ids')
    amount_due = fields.Monetary(compute='_compute_line_ids', currency_field='currency_id',
                                 help="Positive when tax is due, negative when tax is to be recovered.")

    def _default_period(self):
        previous_month = fields.Date.context_today(self) - relativedelta(months=1)
        return date_utils.start_of(previous_month, 'month'), date_utils.end_of(previous_month, 'month')

    def _tax_line_domain(self):
        self.ensure_one()
        domain = Domain([
            ('company_id', '=', self.company_id.id),
            ('parent_state', '=', 'posted'),
            ('date', '>=', self.date_from),
            ('date', '<=', self.date_to),
            ('tax_repartition_line_id.use_in_tax_closing', '=', True),
        ])
        return domain & self.env['account.move.line']._get_tax_exigible_domain()

    @api.depends('company_id', 'date_from', 'date_to')
    def _compute_line_ids(self):
        for wizard in self:
            commands = [Command.clear()]
            total = 0.0
            if wizard.date_from and wizard.date_to and wizard.date_from <= wizard.date_to:
                groups = self.env['account.move.line']._read_group(
                    wizard._tax_line_domain(), ['tax_group_id', 'account_id'], ['balance:sum'])
                for tax_group, account, balance in groups:
                    if wizard.currency_id.is_zero(balance):
                        continue
                    total += balance
                    commands.append(Command.create({
                        'tax_group_id': tax_group.id,
                        'account_id': account.id,
                        'balance': balance,
                    }))
            wizard.line_ids = commands
            wizard.amount_due = -total

    def _check_period(self):
        self.ensure_one()
        if self.date_from > self.date_to:
            raise UserError(self.env._("The start date must be before the end date."))
        overlapping = self.env['account.move'].search([
            ('company_id', '=', self.company_id.id),
            ('state', '=', 'posted'),
            ('ci_tax_closing_date_from', '<=', self.date_to),
            ('ci_tax_closing_date_to', '>=', self.date_from),
        ], limit=1)
        if overlapping:
            raise UserError(self.env._(
                "The tax return of this period is already closed by %(entry)s (%(date_from)s - %(date_to)s). "
                "Reset that entry to draft first to close it again.",
                entry=overlapping.name,
                date_from=format_date(self.env, overlapping.ci_tax_closing_date_from),
                date_to=format_date(self.env, overlapping.ci_tax_closing_date_to)))

    def _prepare_move_vals(self):
        self.ensure_one()
        _ = self.env._
        period = f"{format_date(self.env, self.date_from)} - {format_date(self.env, self.date_to)}"
        line_vals = []
        net_by_group = defaultdict(float)
        for line in self.line_ids:
            net_by_group[line.tax_group_id] += line.balance
            line_vals.append({
                'name': _("Tax return %(period)s: %(account)s", period=period, account=line.account_id.display_name),
                'account_id': line.account_id.id,
                'balance': -line.balance,
            })
        for tax_group, net in net_by_group.items():
            if self.currency_id.is_zero(net):
                continue
            if net < 0:  # more tax collected than paid: due to the administration
                account = tax_group.tax_payable_account_id or self.payable_account_id
            else:
                account = tax_group.tax_receivable_account_id or self.receivable_account_id
            if not account:
                raise UserError(_(
                    "Set a tax %(kind)s account on the tax group %(group)s, or a default one in this wizard.",
                    kind=_("payable") if net < 0 else _("receivable"), group=tax_group.display_name or _("(none)")))
            line_vals.append({
                'name': _("Tax return %(period)s: %(group)s", period=period, group=tax_group.display_name or ''),
                'account_id': account.id,
                'balance': net,
            })
        return {
            'move_type': 'entry',
            'company_id': self.company_id.id,
            'journal_id': self.journal_id.id,
            'date': self.date_to,
            'ref': _("Tax Return %s", period),
            'ci_tax_closing_date_from': self.date_from,
            'ci_tax_closing_date_to': self.date_to,
            'line_ids': [Command.create(vals) for vals in line_vals],
        }

    def action_create_closing(self):
        self.ensure_one()
        self._check_period()
        if not self.line_ids:
            raise UserError(self.env._("There is no tax to close in this period."))
        move = self.env['account.move'].create(self._prepare_move_vals())
        move.action_post()
        if self.set_tax_lock_date and (not self.company_id.tax_lock_date or self.company_id.tax_lock_date < self.date_to):
            wizard = self.env['ci.account.lock.date.wizard'].with_company(self.company_id).create({
                'company_id': self.company_id.id,
            })
            wizard.tax_lock_date = self.date_to
            wizard.action_save()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'res_id': move.id,
            'views': [(False, 'form')],
        }


class CiAccountTaxClosingWizardLine(models.TransientModel):
    _name = 'ci.account.tax.closing.wizard.line'
    _description = "Tax Return Closing Line"

    wizard_id = fields.Many2one('ci.account.tax.closing.wizard', required=True, ondelete='cascade')
    currency_id = fields.Many2one(related='wizard_id.currency_id')
    tax_group_id = fields.Many2one('account.tax.group', readonly=True)
    account_id = fields.Many2one('account.account', readonly=True)
    balance = fields.Monetary(readonly=True, currency_field='currency_id')
