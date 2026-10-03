# -*- coding: utf-8 -*-
from collections import defaultdict

from odoo import models

OPERATING_TYPES = (
    'asset_receivable', 'asset_current', 'asset_prepayments',
    'liability_payable', 'liability_current', 'liability_credit_card',
    'income', 'income_other', 'expense', 'expense_other', 'expense_depreciation', 'expense_direct_cost',
    'equity_unaffected',
)
INVESTING_TYPES = ('asset_fixed', 'asset_non_current')
FINANCING_TYPES = ('liability_non_current', 'equity')
ACTIVITIES = ('operating', 'investing', 'financing', 'unclassified')


class CiAccountReportCashFlow(models.AbstractModel):
    """Cash flow statement (direct method).

    Every movement of a bank/cash account is split over the other lines of its
    journal entry. When such a line is a reconciled clearing line (outstanding
    receipts/payments, suspense, transfer...), the split follows the
    reconciliation to the entry on the other side, so a customer payment shows
    up under the receivable it paid rather than under the outstanding account.
    The activity of a counterpart account comes from its cash flow tag
    (Operating/Investing/Financing Activity) or else from its account type.
    """
    _name = 'ci.account.report.cash.flow'
    _inherit = 'ci.account.report'
    _description = "Cash Flow Statement"

    _ci_filters = ('journals', 'draft', 'unfold_all', 'hide_zero')

    def _ci_activity_names(self):
        _ = self.env._
        return {
            'operating': _("Cash flows from operating activities"),
            'investing': _("Cash flows from investing & extraordinary activities"),
            'financing': _("Cash flows from financing activities"),
            'unclassified': _("Cash flows from unclassified activities"),
        }

    def _ci_tag_activities(self):
        result = {}
        for activity in ('operating', 'investing', 'financing'):
            tag = self.env.ref(f'account.account_tag_{activity}', raise_if_not_found=False)
            if tag:
                result[tag.id] = activity
        return result

    def _ci_account_activity(self, account, tag_activities):
        for tag in account.tag_ids:
            if tag.id in tag_activities:
                return tag_activities[tag.id]
        if account.account_type in OPERATING_TYPES:
            return 'operating'
        if account.account_type in INVESTING_TYPES:
            return 'investing'
        if account.account_type in FINANCING_TYPES:
            return 'financing'
        return 'unclassified'

    def _ci_cash_balance(self, options, date_domain):
        domain = self._ci_base_domain(options) + [('account_id.account_type', '=', 'asset_cash')] + date_domain
        return self._ci_sum_by(options, domain, ()).get((), {}).get('balance', 0.0)

    def _ci_cash_flows(self, options):
        """``{account_id: amount}``: cash received (+) / paid (-) per counterpart account."""
        date_from, date_to = options['date']['date_from'], options['date']['date_to']
        Line = self.env['account.move.line']
        liquidity_domain = self._ci_base_domain(options) + self._ci_date_domain(date_from, date_to) + [
            ('account_id.account_type', '=', 'asset_cash'),
        ]
        cash_by_move = defaultdict(float)
        for move, balance in Line._read_group(liquidity_domain, ['move_id'], ['balance:sum']):
            cash_by_move[move.id] += balance
        flows = defaultdict(float)
        if not cash_by_move:
            return flows
        counterparts = Line.search([
            ('move_id', 'in', list(cash_by_move)),
            ('account_id.account_type', '!=', 'asset_cash'),
        ])
        by_move = defaultdict(lambda: Line)
        for line in counterparts:
            by_move[line.move_id.id] |= line
        currency = self.env.company.currency_id
        for move_id, cash in cash_by_move.items():
            if currency.is_zero(cash):
                continue  # transfer between two cash accounts
            lines = by_move[move_id]
            total = sum(lines.mapped('balance'))
            if currency.is_zero(total):
                continue
            for line in lines:
                # share of the cash movement carried by this counterpart line
                share = cash * line.balance / total
                for account_id, amount in self._ci_follow_reconciliation(line, share):
                    flows[account_id] += amount
        return flows

    def _ci_follow_reconciliation(self, line, amount):
        """Split ``amount`` of ``line`` over the accounts it actually settles."""
        account = line.account_id
        if account.account_type in ('asset_receivable', 'liability_payable') or not account.reconcile:
            return [(account.id, amount)]
        matched = (line.matched_debit_ids.debit_move_id | line.matched_credit_ids.credit_move_id) - line
        others = (matched.move_id.line_ids - matched).filtered(
            lambda l: l.account_id.account_type != 'asset_cash' and l.account_id != account)
        total = sum(others.mapped('balance'))
        if not others or self.env.company.currency_id.is_zero(total):
            return [(account.id, amount)]
        return [(other.account_id.id, amount * other.balance / total) for other in others]

    def _ci_get_lines(self, options):
        _ = self.env._
        date_from, date_to = options['date']['date_from'], options['date']['date_to']
        opening = self._ci_cash_balance(options, [('date', '<', date_from)])
        closing = self._ci_cash_balance(options, [('date', '<=', date_to)])
        flows = self._ci_cash_flows(options)
        accounts = self.env['account.account'].browse(list(flows)).sorted(lambda a: (a.code or '', a.name))
        tag_activities = self._ci_tag_activities()
        by_activity = defaultdict(list)
        for account in accounts:
            by_activity[self._ci_account_activity(account, tag_activities)].append(account)

        lines = [self._ci_line(options, self._build_line_id(('node', 'opening')),
                               _("Cash and cash equivalents, beginning of period"), [opening], css='o_ci_section',
                               hide_if_zero=False)]
        net_id = self._build_line_id(('node', 'net'))
        lines.append(self._ci_line(options, net_id, _("Net increase in cash and cash equivalents"),
                                   [closing - opening], css='o_ci_section', hide_if_zero=False))
        names = self._ci_activity_names()
        for activity in ACTIVITIES:
            activity_accounts = by_activity.get(activity, [])
            if activity == 'unclassified' and not activity_accounts:
                continue
            activity_id = self._build_line_id(('activity', activity))
            lines.append(self._ci_line(
                options, activity_id, names[activity], [sum(flows[a.id] for a in activity_accounts)],
                level=1, parent_id=net_id, css='o_ci_group', unfoldable=bool(activity_accounts), hide_if_zero=False))
            for direction, label in (('in', _("Cash in")), ('out', _("Cash out"))):
                direction_accounts = [a for a in activity_accounts if (flows[a.id] > 0) == (direction == 'in')]
                if not direction_accounts:
                    continue
                direction_id = f"{activity_id}|dir-{direction}"
                lines.append(self._ci_line(options, direction_id, label,
                                           [sum(flows[a.id] for a in direction_accounts)], level=2,
                                           parent_id=activity_id, unfoldable=True))
                for account in direction_accounts:
                    lines.append(self._ci_line(
                        options, f"{direction_id}|acc-{account.id}", self._ci_account_name(account),
                        [flows[account.id]], level=3, parent_id=direction_id,
                        actions=self._ci_line_actions('general_ledger')))
        lines.append(self._ci_line(options, self._build_line_id(('node', 'closing')),
                                   _("Cash and cash equivalents, closing balance"), [closing], css='o_ci_total',
                                   hide_if_zero=False))
        return lines

    def _ci_get_line_domain(self, options, line_id):
        kind, value = self._parse_line_id(line_id)[-1]
        date_from, date_to = options['date']['date_from'], options['date']['date_to']
        if kind == 'acc':
            return self._ci_base_domain(options) + self._ci_date_domain(date_from, date_to) + [
                ('account_id', '=', int(value))]
        return None
