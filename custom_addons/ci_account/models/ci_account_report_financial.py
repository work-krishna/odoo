# -*- coding: utf-8 -*-
from odoo import models

BALANCE_SHEET_TYPES = (
    'asset_receivable', 'asset_cash', 'asset_current', 'asset_non_current', 'asset_prepayments', 'asset_fixed',
    'liability_payable', 'liability_credit_card', 'liability_current', 'liability_non_current', 'equity',
)
PROFIT_LOSS_TYPES = (
    'income', 'income_other', 'expense', 'expense_other', 'expense_depreciation', 'expense_direct_cost',
)


class CiAccountReportFinancial(models.AbstractModel):
    """Statements built from a tree of account-type nodes.

    A node is a dict with a ``key`` and a ``name`` and one of:

    * ``types``: account types; the line unfolds into one line per account
    * ``children``: sub-nodes; ``total`` names an optional total line after them
    * ``special``: a value computed by ``_ci_special_values`` (e.g. earnings)
    * ``formula``: ``callable(values_by_key, period_index) -> value`` over other nodes

    ``sign`` (inherited by the children) turns balances into displayed amounts
    (-1 for credit-natured nodes).
    """
    _name = 'ci.account.report.financial'
    _inherit = 'ci.account.report'
    _description = "Financial Statement"

    _ci_filters = ('comparison', 'journals', 'draft', 'hide_zero', 'unfold_all', 'analytic')
    _ci_growth_column = True

    def _ci_get_tree(self):
        return []

    def _ci_period_balances(self, options, period):
        """``{account_id: balance}`` for one period."""
        return {}

    def _ci_special_values(self, options, period):
        return {}

    # -------------------------------------------------------------------------

    def _ci_get_lines(self, options):
        periods = self._ci_get_periods(options)
        balances = [self._ci_period_balances(options, period) for period in periods]
        specials = [self._ci_special_values(options, period) for period in periods]
        account_ids = {account_id for period_balances in balances for account_id in period_balances}
        accounts = self.env['account.account'].browse(account_ids).sorted(lambda a: (a.code or '', a.name))
        accounts_by_type = {}
        for account in accounts:
            accounts_by_type.setdefault(account.account_type, []).append(account)

        values_by_key = {}
        lines = []
        tree = self._ci_get_tree()
        for node in tree:
            self._ci_compute_node(node, 1, balances, specials, accounts_by_type, values_by_key)
        for node in tree:
            lines += self._ci_render_node(options, node, 0, None, values_by_key, balances, accounts_by_type)
        return lines

    def _ci_compute_node(self, node, sign, balances, specials, accounts_by_type, values_by_key):
        sign = node.get('sign', sign)
        node['_sign'] = sign
        nb_periods = len(balances)
        if 'children' in node:
            values = [0.0] * nb_periods
            for child in node['children']:
                child_values = self._ci_compute_node(child, sign, balances, specials, accounts_by_type, values_by_key)
                if not child.get('formula'):
                    values = [a + b for a, b in zip(values, child_values)]
        elif 'types' in node:
            values = [
                sign * sum(balances[index].get(account.id, 0.0)
                           for account_type in node['types'] for account in accounts_by_type.get(account_type, []))
                for index in range(nb_periods)
            ]
        elif 'special' in node:
            values = [sign * specials[index].get(node['special'], 0.0) for index in range(nb_periods)]
        else:
            values = [0.0] * nb_periods
        values_by_key[node['key']] = values
        return values

    def _ci_render_node(self, options, node, level, parent_id, values_by_key, balances, accounts_by_type):
        line_id = self._build_line_id(('node', node['key']))
        if node.get('formula'):
            values = [node['formula'](values_by_key, index) for index in range(len(balances))]
            values_by_key[node['key']] = values
            return [self._ci_line(options, line_id, node['name'], values, level=level, parent_id=parent_id,
                                  css='o_ci_total', unfoldable=False)]
        values = values_by_key[node['key']]
        sign = node['_sign']
        if 'children' in node:
            css = 'o_ci_section' if level == 0 else 'o_ci_group'
            lines = [self._ci_line(options, line_id, node['name'], [] if node.get('total') else values,
                                   level=level, parent_id=parent_id, css=css, unfoldable=False)]
            for child in node['children']:
                lines += self._ci_render_node(options, child, level + 1, line_id, values_by_key, balances,
                                              accounts_by_type)
            if node.get('total'):
                lines.append(self._ci_line(options, self._build_line_id(('total', node['key'])), node['total'],
                                           values, level=level, parent_id=parent_id, css='o_ci_total'))
            return lines
        if 'types' in node:
            accounts = [account for account_type in node['types'] for account in accounts_by_type.get(account_type, [])]
            lines = [self._ci_line(options, line_id, node['name'], values, level=level, parent_id=parent_id,
                                   css='o_ci_group', unfoldable=bool(accounts),
                                   actions=self._ci_line_actions('journal_items'))]
            for account in accounts:
                account_values = [sign * period_balances.get(account.id, 0.0) for period_balances in balances]
                lines.append(self._ci_line(
                    options, self._build_line_id(('acc', account.id)), self._ci_account_name(account),
                    account_values, level=level + 1, parent_id=line_id,
                    actions=self._ci_line_actions('general_ledger', 'journal_items')))
            return lines
        return [self._ci_line(options, line_id, node['name'], values, level=level, parent_id=parent_id,
                              css='o_ci_group', hide_if_zero=False, actions=self._ci_line_actions('journal_items'))]

    def _ci_find_node(self, key, nodes=None):
        for node in self._ci_get_tree() if nodes is None else nodes:
            if node['key'] == key:
                return node
            found = self._ci_find_node(key, node.get('children', []))
            if found:
                return found
        return None

    def _ci_node_types(self, node):
        if 'types' in node:
            return list(node['types'])
        return [t for child in node.get('children', []) for t in self._ci_node_types(child)]


class CiAccountReportBalanceSheet(models.AbstractModel):
    _name = 'ci.account.report.balance.sheet'
    _inherit = 'ci.account.report.financial'
    _description = "Balance Sheet"

    _ci_date_mode = 'single'
    _ci_default_date_filter = 'today'

    def _ci_get_tree(self):
        _ = self.env._
        return [
            {'key': 'assets', 'name': _("ASSETS"), 'total': _("Total ASSETS"), 'sign': 1, 'children': [
                {'key': 'current_assets', 'name': _("Current Assets"), 'total': _("Total Current Assets"), 'children': [
                    {'key': 'asset_cash', 'name': _("Bank and Cash Accounts"), 'types': ['asset_cash']},
                    {'key': 'asset_receivable', 'name': _("Receivables"), 'types': ['asset_receivable']},
                    {'key': 'asset_current', 'name': _("Current Assets"), 'types': ['asset_current']},
                    {'key': 'asset_prepayments', 'name': _("Prepayments"), 'types': ['asset_prepayments']},
                ]},
                {'key': 'asset_fixed', 'name': _("Plus Fixed Assets"), 'types': ['asset_fixed']},
                {'key': 'asset_non_current', 'name': _("Plus Non-current Assets"), 'types': ['asset_non_current']},
            ]},
            {'key': 'liabilities', 'name': _("LIABILITIES"), 'total': _("Total LIABILITIES"), 'sign': -1, 'children': [
                {'key': 'current_liabilities', 'name': _("Current Liabilities"),
                 'total': _("Total Current Liabilities"), 'children': [
                    {'key': 'liability_current', 'name': _("Current Liabilities"), 'types': ['liability_current']},
                    {'key': 'liability_payable', 'name': _("Payables"), 'types': ['liability_payable']},
                    {'key': 'liability_credit_card', 'name': _("Credit Cards"), 'types': ['liability_credit_card']},
                ]},
                {'key': 'liability_non_current', 'name': _("Plus Non-current Liabilities"),
                 'types': ['liability_non_current']},
            ]},
            {'key': 'equity', 'name': _("EQUITY"), 'total': _("Total EQUITY"), 'sign': -1, 'children': [
                {'key': 'unallocated_earnings', 'name': _("Unallocated Earnings"),
                 'total': _("Total Unallocated Earnings"), 'children': [
                    {'key': 'current_year_earnings', 'name': _("Current Year Unallocated Earnings"),
                     'special': 'current_year_earnings'},
                    {'key': 'previous_years_earnings', 'name': _("Previous Years Unallocated Earnings"),
                     'special': 'previous_years_earnings'},
                ]},
                {'key': 'retained_earnings', 'name': _("Retained Earnings"), 'types': ['equity']},
            ]},
            {'key': 'liabilities_equity', 'name': _("LIABILITIES + EQUITY"),
             'formula': lambda values, index: values['liabilities'][index] + values['equity'][index]},
        ]

    def _ci_period_balances(self, options, period):
        domain = self._ci_base_domain(options) + [
            ('date', '<=', period['date_to']),
            ('account_id.account_type', 'in', BALANCE_SHEET_TYPES),
        ]
        groups = self._ci_sum_by(options, domain, ['account_id'], date_to=period['date_to'])
        return {key[0]: values['balance'] for key, values in groups.items()}

    def _ci_special_values(self, options, period):
        fy_start = self._ci_fiscal_year_start(period['date_to'])
        base = self._ci_base_domain(options) + self._ci_pl_account_domain()
        current = self._ci_sum_by(options, base + [('date', '>=', fy_start), ('date', '<=', period['date_to'])], (),
                                  date_to=period['date_to'])
        previous = self._ci_sum_by(options, base + [('date', '<', fy_start)], (), date_to=period['date_to'])
        return {
            'current_year_earnings': current.get((), {}).get('balance', 0.0),
            'previous_years_earnings': previous.get((), {}).get('balance', 0.0),
        }

    def _ci_get_line_domain(self, options, line_id):
        kind, value = self._parse_line_id(line_id)[-1]
        date_to = options['date']['date_to']
        base = self._ci_base_domain(options)
        fy_start = options['date']['date_from']
        if kind == 'acc':
            account = self.env['account.account'].browse(int(value))
            dates = [('date', '<=', date_to)]
            if not account.include_initial_balance:
                dates.append(('date', '>=', fy_start))
            return base + [('account_id', '=', account.id)] + dates
        if kind == 'node':
            if value == 'current_year_earnings':
                return base + self._ci_pl_account_domain() + [('date', '>=', fy_start), ('date', '<=', date_to)]
            if value == 'previous_years_earnings':
                return base + self._ci_pl_account_domain() + [('date', '<', fy_start)]
            node = self._ci_find_node(value)
            types = node and self._ci_node_types(node)
            if types:
                return base + [('account_id.account_type', 'in', types), ('date', '<=', date_to)]
        return None


class CiAccountReportProfitLoss(models.AbstractModel):
    _name = 'ci.account.report.profit.loss'
    _inherit = 'ci.account.report.financial'
    _description = "Profit and Loss"

    def _ci_get_tree(self):
        _ = self.env._
        return [
            {'key': 'revenue', 'name': _("Revenue"), 'types': ['income'], 'sign': -1},
            {'key': 'cost_of_revenue', 'name': _("Less Costs of Revenue"), 'types': ['expense_direct_cost'], 'sign': 1},
            {'key': 'gross_profit', 'name': _("GROSS PROFIT"),
             'formula': lambda v, i: v['revenue'][i] - v['cost_of_revenue'][i]},
            {'key': 'operating_expenses', 'name': _("Less Operating Expenses"),
             'total': _("Total Operating Expenses"), 'sign': 1, 'children': [
                {'key': 'expense', 'name': _("Expenses"), 'types': ['expense']},
                {'key': 'expense_depreciation', 'name': _("Depreciation"), 'types': ['expense_depreciation']},
            ]},
            {'key': 'operating_income', 'name': _("OPERATING INCOME"),
             'formula': lambda v, i: v['gross_profit'][i] - v['operating_expenses'][i]},
            {'key': 'other_income', 'name': _("Plus Other Income"), 'types': ['income_other'], 'sign': -1},
            {'key': 'other_expenses', 'name': _("Less Other Expenses"), 'types': ['expense_other'], 'sign': 1},
            {'key': 'net_profit', 'name': _("NET PROFIT"),
             'formula': lambda v, i: v['operating_income'][i] + v['other_income'][i] - v['other_expenses'][i]},
        ]

    def _ci_period_balances(self, options, period):
        domain = self._ci_base_domain(options) + [
            ('date', '>=', period['date_from']), ('date', '<=', period['date_to']),
            ('account_id.account_type', 'in', PROFIT_LOSS_TYPES),
        ]
        groups = self._ci_sum_by(options, domain, ['account_id'], date_to=period['date_to'])
        return {key[0]: values['balance'] for key, values in groups.items()}

    def _ci_get_line_domain(self, options, line_id):
        kind, value = self._parse_line_id(line_id)[-1]
        dates = [('date', '>=', options['date']['date_from']), ('date', '<=', options['date']['date_to'])]
        base = self._ci_base_domain(options) + dates
        if kind == 'acc':
            return base + [('account_id', '=', int(value))]
        if kind == 'node':
            node = self._ci_find_node(value)
            types = node and self._ci_node_types(node)
            if types:
                return base + [('account_id.account_type', 'in', types)]
            if value in ('gross_profit', 'operating_income', 'net_profit'):
                return base + [('account_id.account_type', 'in', PROFIT_LOSS_TYPES)]
        return None
