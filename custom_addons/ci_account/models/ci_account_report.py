# -*- coding: utf-8 -*-
import io
from collections import defaultdict
from datetime import timedelta

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools import date_utils, format_date
from odoo.tools.misc import formatLang

try:
    import xlsxwriter
except ImportError:  # pragma: no cover - declared in external_dependencies
    xlsxwriter = None

LINE_ID_SEPARATOR = '|'
# account types whose balance restarts at each fiscal year (cf. account.account.include_initial_balance)
FISCAL_YEAR_RESET_TYPES = (
    'income', 'income_other', 'expense', 'expense_other', 'expense_depreciation', 'expense_direct_cost',
    'equity_unaffected',
)
LOAD_MORE_LIMIT = 200


class CiAccountReport(models.AbstractModel):
    """Base of every ci_account financial report.

    A report is an abstract model inheriting this one. It declares its filters
    and columns and builds its lines; this base handles options (dates,
    comparison periods, journals, partners, analytic accounts), folding, lazy
    expansion, drill-down to journal items and the PDF/XLSX exports.

    A line is a dict::

        {'id': 'acc-12', 'parent_id': 'grp-asset_cash' or None, 'name': ...,
         'level': 0.., 'columns': [{'name': formatted, 'no_format': raw, 'figure': ...}],
         'class': 'o_ci_total' / 'o_ci_section' / ..., 'unfoldable': bool, 'unfolded': bool,
         'lazy': bool (children are fetched with get_expanded_lines), 'actions': [...]}

    Line ids are chains of ``<kind>-<value>`` joined by ``|``; ``_parse_line_id``
    turns them back into ``[(kind, value), ...]``.
    """
    _name = 'ci.account.report'
    _description = "Accounting Report"

    # --- what a report declares --------------------------------------------
    _ci_date_mode = 'range'  # 'range' (from - to) or 'single' (as of a date)
    _ci_default_date_filter = 'this_year'
    # subset of: comparison, journals, draft, hide_zero, unfold_all, hierarchy,
    # partner, analytic, account_type, aging, unreconciled
    _ci_filters = ()
    _ci_growth_column = False  # add a % column when comparing with one period
    _ci_landscape = False
    _ci_default_account_type = 'both'

    # -------------------------------------------------------------------------
    # PUBLIC API (called by the client action and the export controller)
    # -------------------------------------------------------------------------

    @api.model
    def get_report_information(self, previous_options=None):
        self._ci_check_access()
        options = self._ci_get_options(previous_options)
        lines = self._ci_get_all_lines(options, expand_lazy=True)
        return {
            'title': self._ci_get_title(options),
            'options': options,
            'filters': list(self._ci_get_filters(options)),
            'date_mode': options['date']['mode'],
            'column_groups': self._ci_get_column_groups(options),
            'columns': self._ci_get_all_columns(options),
            'lines': lines,
            'buttons': self._ci_get_buttons(options),
            'warnings': self._ci_get_warnings(options),
            'show_analytic': self.env.user.has_group('analytic.group_analytic_accounting'),
        }

    @api.model
    def get_expanded_lines(self, options, line_id, load_more=None):
        self._ci_check_access()
        options = self._ci_get_options(options)
        load_more = load_more or {}
        lines = self._ci_expand_line(options, line_id, offset=load_more.get('offset', 0),
                                     progress=load_more.get('progress'), limit=LOAD_MORE_LIMIT)
        return self._ci_postprocess_lines(options, lines)

    @api.model
    def action_open_line(self, options, line_id, target='journal_items'):
        """Drill-down: journal items behind a line, its general ledger, or the
        document of a journal item line."""
        self._ci_check_access()
        options = self._ci_get_options(options)
        parsed = self._parse_line_id(line_id)
        kind, value = parsed[-1]
        if target == 'record' and kind == 'aml':
            move = self.env['account.move.line'].browse(int(value)).move_id
            return self._ci_action_open_move(move)
        if target == 'record' and kind == 'move':
            return self._ci_action_open_move(self.env['account.move'].browse(int(value)))
        if target == 'general_ledger' and kind == 'acc':
            return self._ci_action_general_ledger(options, [int(value)])
        domain = self._ci_get_line_domain(options, line_id)
        if domain is None:
            return False
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._("Journal Items"),
            'res_model': 'account.move.line',
            'views': [(self.env.ref('account.view_move_line_tree').id, 'list'), (False, 'form')],
            'domain': domain,
            'context': {'search_default_group_by_account': 0, 'create': False},
            'target': 'current',
        }

    # -------------------------------------------------------------------------
    # TO OVERRIDE
    # -------------------------------------------------------------------------

    def _ci_get_title(self, options):
        return self._description

    def _ci_get_filters(self, options):
        return self._ci_filters

    def _ci_get_date_mode(self, previous):
        """'range' (from - to) or 'single' (as of a date); ``previous`` are the
        options received from the client."""
        return self._ci_date_mode

    def _ci_get_default_date_filter(self, previous):
        return self._ci_default_date_filter

    def _ci_get_columns(self, options):
        """Columns of one period: list of {'name', 'figure', 'blank_if_zero'}."""
        return [{'name': self.env._("Balance"), 'figure': 'monetary'}]

    def _ci_get_lines(self, options):
        """Top-level (and eagerly computed) lines of the report."""
        return []

    def _ci_expand_line(self, options, line_id, offset=0, progress=None, limit=None):
        """Children of a lazy line."""
        return []

    def _ci_get_line_domain(self, options, line_id):
        """Journal items behind a line (None = no drill-down)."""
        return None

    def _ci_get_buttons(self, options):
        return []

    def _ci_get_warnings(self, options):
        warnings = []
        currencies = self._ci_companies().currency_id
        if len(currencies) > 1:
            warnings.append(self.env._(
                "The selected companies use different currencies; amounts are converted to %(currency)s "
                "at the rate of the report date.", currency=self.env.company.currency_id.name))
        return warnings

    # -------------------------------------------------------------------------
    # OPTIONS
    # -------------------------------------------------------------------------

    def _ci_check_access(self):
        if not self.env.user.has_group('account.group_account_readonly'):
            raise UserError(self.env._("You are not allowed to see accounting reports."))

    def _ci_companies(self):
        return self.env.companies

    @api.model
    def _ci_get_options(self, previous=None):
        previous = previous or {}
        today = fields.Date.context_today(self)
        filters = self._ci_get_filters(previous)
        date_mode = self._ci_get_date_mode(previous)
        options = {
            'report_model': self._name,
            'date': self._ci_init_date(previous.get('date') or {}, today, date_mode,
                                       self._ci_get_default_date_filter(previous)),
            'unfolded_lines': [lid for lid in previous.get('unfolded_lines') or [] if isinstance(lid, str)],
            'unfold_all': bool(previous.get('unfold_all')) if 'unfold_all' in filters else False,
            'all_entries': bool(previous.get('all_entries')) if 'draft' in filters else False,
            'hide_zero': previous.get('hide_zero', True) if 'hide_zero' in filters else False,
            'hierarchy': bool(previous.get('hierarchy')) if 'hierarchy' in filters else False,
            'unreconciled': bool(previous.get('unreconciled')) if 'unreconciled' in filters else False,
            'account_ids': [int(a) for a in previous.get('account_ids') or []],
            'partner_ids': [int(p) for p in previous.get('partner_ids') or []] if 'partner' in filters else [],
            'analytic_account_ids': [int(a) for a in previous.get('analytic_account_ids') or []]
            if 'analytic' in filters else [],
            'company_ids': self._ci_companies().ids,
        }
        if 'account_type' in filters:
            account_type = previous.get('account_type') or self._ci_default_account_type
            options['account_type'] = account_type if account_type in ('receivable', 'payable', 'both') else 'both'
        if 'aging' in filters:
            options['aging_based_on'] = 'invoice_date' if previous.get('aging_based_on') == 'invoice_date' else 'due_date'
        if 'journals' in filters:
            options['journals'] = self._ci_init_journals(previous.get('journals'))
        options['comparison'] = self._ci_init_comparison(previous.get('comparison') or {}, options['date']) \
            if 'comparison' in filters else {'filter': 'no_comparison', 'number_period': 1, 'periods': []}
        return options

    def _ci_init_journals(self, previous):
        selected = {j['id'] for j in previous or [] if j.get('selected')}
        journals = self.env['account.journal'].search(
            [('company_id', 'in', self._ci_companies().ids)], order='company_id, sequence, type, code')
        return [{
            'id': journal.id,
            'name': journal.name,
            'code': journal.code,
            'type': journal.type,
            'selected': journal.id in selected,
        } for journal in journals]

    def _ci_init_date(self, previous, today, date_mode, default_filter):
        date_filter = previous.get('filter') or default_filter
        if date_filter == 'custom':
            date_to = fields.Date.to_date(previous.get('date_to')) or today
            date_from = fields.Date.to_date(previous.get('date_from')) or date_utils.start_of(date_to, 'month')
        else:
            date_from, date_to = self._ci_compute_period(date_filter, today)
        if date_mode == 'single':
            date_from = self.env.company.compute_fiscalyear_dates(date_to)['date_from']
        elif date_from > date_to:
            date_from, date_to = date_to, date_from
        return {
            'filter': date_filter,
            'mode': date_mode,
            'date_from': fields.Date.to_string(date_from),
            'date_to': fields.Date.to_string(date_to),
            'string': self._ci_period_string(date_filter, date_from, date_to, date_mode),
        }

    def _ci_compute_period(self, date_filter, today):
        company = self.env.company
        if date_filter == 'today':
            return today, today
        if date_filter in ('this_month', 'last_month'):
            ref = today if date_filter == 'this_month' else today - relativedelta(months=1)
            return date_utils.start_of(ref, 'month'), date_utils.end_of(ref, 'month')
        if date_filter in ('this_quarter', 'last_quarter'):
            ref = today if date_filter == 'this_quarter' else today - relativedelta(months=3)
            return date_utils.get_quarter(ref)
        fiscal_year = company.compute_fiscalyear_dates(today)
        if date_filter == 'last_year':
            fiscal_year = company.compute_fiscalyear_dates(fiscal_year['date_from'] - timedelta(days=1))
        return fiscal_year['date_from'], fiscal_year['date_to']

    def _ci_period_string(self, date_filter, date_from, date_to, date_mode):
        _ = self.env._
        if date_mode == 'single':
            return _("As of %s", format_date(self.env, date_to))
        if date_filter in ('this_month', 'last_month'):
            return format_date(self.env, date_to, date_format='MMM yyyy')
        if date_filter in ('this_quarter', 'last_quarter'):
            return _("Q%(quarter)s %(year)s", quarter=date_utils.get_quarter_number(date_to), year=date_to.year)
        if date_filter in ('this_year', 'last_year'):
            return self._ci_fiscal_year_name(date_from, date_to)
        return _("From %(date_from)s to %(date_to)s",
                 date_from=format_date(self.env, date_from), date_to=format_date(self.env, date_to))

    def _ci_fiscal_year_name(self, date_from, date_to):
        return self.env.company._ci_fiscal_year_name(date_from, date_to)

    def _ci_init_comparison(self, previous, date_options):
        comparison_filter = previous.get('filter')
        if comparison_filter not in ('previous_period', 'same_last_year'):
            comparison_filter = 'no_comparison'
        try:
            number_period = max(1, min(12, int(previous.get('number_period') or 1)))
        except (TypeError, ValueError):
            number_period = 1
        periods = []
        if comparison_filter != 'no_comparison':
            date_from = fields.Date.to_date(date_options['date_from'])
            date_to = fields.Date.to_date(date_options['date_to'])
            for _index in range(number_period):
                date_from, date_to = self._ci_previous_period(
                    comparison_filter, date_options['filter'], date_from, date_to, date_options['mode'])
                periods.append({
                    'date_from': fields.Date.to_string(date_from),
                    'date_to': fields.Date.to_string(date_to),
                    'string': self._ci_period_string(date_options['filter'], date_from, date_to,
                                                     date_options['mode']),
                })
        return {'filter': comparison_filter, 'number_period': number_period, 'periods': periods}

    def _ci_previous_period(self, comparison_filter, date_filter, date_from, date_to, date_mode):
        company = self.env.company
        if comparison_filter == 'same_last_year':
            new_to = date_to - relativedelta(years=1)
            if date_to == date_utils.end_of(date_to, 'month'):
                new_to = date_utils.end_of(new_to, 'month')
            new_from = date_from - relativedelta(years=1)
        elif date_filter in ('this_month', 'last_month'):
            ref = date_to - relativedelta(months=1)
            new_from, new_to = date_utils.start_of(ref, 'month'), date_utils.end_of(ref, 'month')
        elif date_filter in ('this_quarter', 'last_quarter'):
            new_from, new_to = date_utils.get_quarter(date_to - relativedelta(months=3))
        elif date_filter in ('this_year', 'last_year'):
            fiscal_year = company.compute_fiscalyear_dates(date_from - timedelta(days=1))
            new_from, new_to = fiscal_year['date_from'], fiscal_year['date_to']
        elif date_mode == 'single':
            new_to = date_from - timedelta(days=1)
            new_from = company.compute_fiscalyear_dates(new_to)['date_from']
        else:
            length = date_to - date_from
            new_to = date_from - timedelta(days=1)
            new_from = new_to - length
        if date_mode == 'single':
            new_from = company.compute_fiscalyear_dates(new_to)['date_from']
        return new_from, new_to

    def _ci_get_periods(self, options):
        """Main period followed by the comparison periods, as dicts with dates."""
        periods = [options['date']] + options['comparison']['periods']
        return [{
            'date_from': fields.Date.to_date(period['date_from']),
            'date_to': fields.Date.to_date(period['date_to']),
            'string': period['string'],
        } for period in periods]

    # -------------------------------------------------------------------------
    # COLUMNS
    # -------------------------------------------------------------------------

    def _ci_has_growth(self, options):
        return self._ci_growth_column and len(options['comparison']['periods']) == 1

    def _ci_get_column_groups(self, options):
        """Header row above the columns: one group per period (+ growth)."""
        periods = self._ci_get_periods(options)
        if len(periods) == 1:
            return []
        span = len(self._ci_get_columns(options))
        groups = [{'name': period['string'], 'colspan': span} for period in periods]
        if self._ci_has_growth(options):
            groups.append({'name': '%', 'colspan': 1})
        return groups

    def _ci_get_all_columns(self, options):
        columns = []
        for _period in self._ci_get_periods(options):
            columns += self._ci_get_columns(options)
        if self._ci_has_growth(options):
            columns.append({'name': '%', 'figure': 'percentage'})
        return columns

    # -------------------------------------------------------------------------
    # LINES
    # -------------------------------------------------------------------------

    @api.model
    def _build_line_id(self, *parts):
        return LINE_ID_SEPARATOR.join(f'{kind}-{value}' for kind, value in parts)

    @api.model
    def _parse_line_id(self, line_id):
        parsed = []
        for part in (line_id or '').split(LINE_ID_SEPARATOR):
            kind, _sep, value = part.partition('-')
            parsed.append((kind, value))
        return parsed

    def _ci_line(self, options, line_id, name, values=(), level=0, parent_id=None, css='',
                 unfoldable=False, lazy=False, unfolded=None, actions=(), hide_if_zero=True, extra=None):
        """Build a line. ``values`` is the flat list of raw values matching
        ``_ci_get_all_columns`` (without the growth column, added here)."""
        columns_def = self._ci_get_all_columns(options)
        values = list(values)
        if self._ci_has_growth(options):
            values = values[:len(columns_def) - 1]
            values.append(self._ci_growth(values[0], values[1]) if len(values) >= 2 else None)
        if unfolded is None:
            unfolded = options.get('unfold_all') or line_id in options.get('unfolded_lines', [])
        line = {
            'id': line_id,
            'parent_id': parent_id,
            'name': name,
            'level': level,
            'class': css,
            'unfoldable': unfoldable,
            'unfolded': bool(unfoldable and unfolded),
            'lazy': lazy,
            'actions': list(actions),
            'hide_if_zero': hide_if_zero,
            'columns': [self._ci_cell(value, col) for value, col in zip(values, columns_def)],
        }
        if len(values) < len(columns_def):
            line['columns'] += [self._ci_cell(None, col) for col in columns_def[len(values):]]
        if extra:
            line.update(extra)
        return line

    def _ci_growth(self, current, previous):
        if not isinstance(current, (int, float)) or not isinstance(previous, (int, float)):
            return None
        currency = self.env.company.currency_id
        if currency.is_zero(previous):
            return None
        return (current - previous) / abs(previous) * 100.0

    def _ci_cell(self, value, column):
        figure = column.get('figure', 'monetary')
        return {
            'name': self._ci_format(value, figure, blank_if_zero=column.get('blank_if_zero')),
            'no_format': value if isinstance(value, (int, float)) else None,
            'figure': figure,
        }

    def _ci_format(self, value, figure='monetary', blank_if_zero=False):
        if value is None or value is False:
            return ''
        if figure == 'monetary':
            currency = self.env.company.currency_id
            if blank_if_zero and currency.is_zero(value):
                return ''
            return formatLang(self.env, currency.round(value) + 0.0, currency_obj=currency)
        if figure == 'percentage':
            return f"{value:.1f}%"
        if figure == 'date':
            return format_date(self.env, value)
        if figure == 'float':
            return formatLang(self.env, value)
        return str(value)

    def _ci_get_all_lines(self, options, expand_lazy=True):
        """Lines of the report, with the children of unfolded lazy lines."""
        lines = self._ci_get_lines(options)
        if expand_lazy:
            expanded = []
            for line in lines:
                expanded.append(line)
                expanded += self._ci_expand_unfolded(options, line)
            lines = expanded
        return self._ci_postprocess_lines(options, lines)

    def _ci_expand_unfolded(self, options, line, limit=None):
        if not (line.get('lazy') and line.get('unfolded')):
            return []
        result = []
        for child in self._ci_expand_line(options, line['id'], limit=limit):
            result.append(child)
            result += self._ci_expand_unfolded(options, child, limit=limit)
        return result

    def _ci_postprocess_lines(self, options, lines):
        if not options.get('hide_zero'):
            return lines
        currency = self.env.company.currency_id
        result = []
        for line in lines:
            if line.get('hide_if_zero') and not line.get('class') \
                    and all(currency.is_zero(col['no_format'] or 0.0) for col in line['columns']
                            if col['figure'] == 'monetary'):
                continue
            result.append(line)
        return result

    # -------------------------------------------------------------------------
    # QUERIES
    # -------------------------------------------------------------------------

    def _ci_base_domain(self, options):
        domain = [
            ('company_id', 'in', self._ci_companies().ids),
            ('account_id', '!=', False),
            ('parent_state', '!=', 'cancel') if options.get('all_entries') else ('parent_state', '=', 'posted'),
        ]
        journal_ids = [j['id'] for j in options.get('journals') or [] if j['selected']]
        if journal_ids:
            domain.append(('journal_id', 'in', journal_ids))
        if options.get('account_ids'):
            domain.append(('account_id', 'in', options['account_ids']))
        if options.get('partner_ids'):
            domain.append(('partner_id', 'child_of', options['partner_ids']))
        if options.get('analytic_account_ids'):
            domain.append(('analytic_distribution', 'in', options['analytic_account_ids']))
        return domain

    def _ci_date_domain(self, date_from=None, date_to=None, strict_before=None):
        domain = []
        if date_from:
            domain.append(('date', '>=', date_from))
        if date_to:
            domain.append(('date', '<=', date_to))
        if strict_before:
            domain.append(('date', '<', strict_before))
        return domain

    def _ci_sum_by(self, options, domain, groupby, date_to=None):
        """Sum debit/credit/balance of journal items grouped by ``groupby`` (field
        names). Returns ``{key: {'debit', 'credit', 'balance'}}`` where key is a
        tuple of ids/values. Companies in another currency are converted to the
        current company's currency at ``date_to``."""
        companies = self._ci_companies()
        main_currency = self.env.company.currency_id
        convert = any(company.currency_id != main_currency for company in companies)
        group_fields = list(groupby) + (['company_id'] if convert else [])
        groups = self.env['account.move.line']._read_group(
            domain, group_fields, ['debit:sum', 'credit:sum', 'balance:sum'])
        result = defaultdict(lambda: {'debit': 0.0, 'credit': 0.0, 'balance': 0.0})
        conversion_date = date_to or fields.Date.context_today(self)
        for group in groups:
            keys = group[:len(group_fields)]
            debit, credit, balance = group[len(group_fields):]
            if convert:
                company = keys[-1]
                keys = keys[:-1]
                if company.currency_id != main_currency:
                    rate_args = (main_currency, self.env.company, conversion_date)
                    debit = company.currency_id._convert(debit, *rate_args)
                    credit = company.currency_id._convert(credit, *rate_args)
                    balance = company.currency_id._convert(balance, *rate_args)
            key = tuple(k.id if isinstance(k, models.BaseModel) else k for k in keys)
            values = result[key]
            values['debit'] += debit
            values['credit'] += credit
            values['balance'] += balance
        return result

    def _ci_fiscal_year_start(self, date):
        return self.env.company.compute_fiscalyear_dates(date)['date_from']

    def _ci_pl_account_domain(self):
        """Accounts reset at each fiscal year: income, expense and current year earnings.
        (``include_initial_balance``'s search method ignores its value, hence the types.)"""
        return [('account_id.account_type', 'in', FISCAL_YEAR_RESET_TYPES)]

    def _ci_bs_account_domain(self):
        return [('account_id.account_type', 'not in', FISCAL_YEAR_RESET_TYPES)]

    def _ci_initial_balances(self, options, date_from, groupby=('account_id',), extra_domain=None):
        """Balances before ``date_from``: from the beginning for balance sheet
        accounts, from the fiscal year start for income/expense accounts (the
        earnings of previous years are in ``_ci_undistributed_earnings``)."""
        base = self._ci_base_domain(options) + (extra_domain or [])
        fy_start = self._ci_fiscal_year_start(date_from)
        balance_sheet = self._ci_sum_by(
            options, base + self._ci_bs_account_domain() + [('date', '<', date_from)], groupby, date_to=date_from)
        profit_loss = self._ci_sum_by(
            options, base + self._ci_pl_account_domain() + [('date', '>=', fy_start), ('date', '<', date_from)],
            groupby, date_to=date_from)
        for key, values in profit_loss.items():
            target = balance_sheet[key]
            for field in ('debit', 'credit', 'balance'):
                target[field] += values[field]
        return balance_sheet

    def _ci_undistributed_earnings(self, options, date_from):
        """Income and expenses of the fiscal years before the one of ``date_from``."""
        base = self._ci_base_domain({**options, 'account_ids': []})
        fy_start = self._ci_fiscal_year_start(date_from)
        groups = self._ci_sum_by(options, base + self._ci_pl_account_domain() + [('date', '<', fy_start)], (),
                                 date_to=date_from)
        return groups.get((), {}).get('balance', 0.0)

    def _ci_account_initial(self, options, account_id=None):
        """Initial balances by account (see ``_ci_initial_balances``). The
        earnings of previous fiscal years are added to the current year
        earnings account; without such an account they are returned apart."""
        date_from = fields.Date.to_date(options['date']['date_from'])
        extra = [('account_id', '=', account_id)] if account_id else None
        initial = self._ci_initial_balances(options, date_from, extra_domain=extra)
        unaffected = self._ci_unaffected_earnings_account()
        shown = {account_id} if account_id else set(options.get('account_ids') or [])
        if shown and (not unaffected or unaffected.id not in shown):
            return initial, 0.0
        undistributed = self._ci_undistributed_earnings(options, date_from)
        if unaffected:
            initial[(unaffected.id,)]['balance'] += undistributed
            return initial, 0.0
        return initial, undistributed

    def _ci_unaffected_earnings_account(self):
        return self.env['account.account'].search([
            ('company_ids', 'in', self.env.company.id),
            ('account_type', '=', 'equity_unaffected'),
        ], limit=1)

    def _ci_account_name(self, account):
        return f"{account.code} {account.name}" if account.code else account.name

    def _ci_line_actions(self, *targets):
        labels = {
            'journal_items': self.env._("Journal Items"),
            'general_ledger': self.env._("General Ledger"),
            'record': self.env._("Open"),
        }
        return [{'target': target, 'name': labels[target]} for target in targets]

    def _ci_action_open_move(self, move):
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'res_id': move.id,
            'views': [(False, 'form')],
            'target': 'current',
        }

    def _ci_action_general_ledger(self, options, account_ids):
        action = self.env['ir.actions.actions']._for_xml_id('ci_account.action_ci_report_general_ledger')
        action['context'] = {
            'report_model': 'ci.account.report.general.ledger',
            'ci_report_options': {
                # as of a date (balance sheet): the fiscal year up to that date
                'date': {
                    'filter': 'custom',
                    'date_from': options['date']['date_from'],
                    'date_to': options['date']['date_to'],
                },
                'account_ids': account_ids,
                'unfolded_lines': [self._build_line_id(('acc', account_id)) for account_id in account_ids],
                'all_entries': options.get('all_entries'),
                'journals': options.get('journals'),
            },
        }
        return action

    # -------------------------------------------------------------------------
    # EXPORT
    # -------------------------------------------------------------------------

    def _ci_export_data(self, options):
        options = self._ci_get_options(options)
        lines = self._ci_get_lines(options)
        all_lines = []
        for line in lines:
            all_lines.append(line)
            all_lines += self._ci_expand_unfolded(options, line, limit=None)
        all_lines = self._ci_postprocess_lines(options, all_lines)
        return options, self._ci_visible_lines(all_lines)

    def _ci_visible_lines(self, lines):
        """Lines whose ancestors are all unfolded (what the user sees)."""
        by_id = {line['id']: line for line in lines}
        visible = []
        for line in lines:
            parent = by_id.get(line['parent_id'])
            hidden = False
            while parent:
                if parent.get('unfoldable') and not parent.get('unfolded'):
                    hidden = True
                    break
                parent = by_id.get(parent['parent_id'])
            if not hidden:
                visible.append(line)
        return visible

    def _ci_filters_summary(self, options):
        """Human readable summary of the options, printed on exports."""
        _ = self.env._
        parts = [options['date']['string']]
        if options['comparison']['periods']:
            parts.append(_("Compared with: %s", ', '.join(p['string'] for p in options['comparison']['periods'])))
        journals = [j['code'] for j in options.get('journals') or [] if j['selected']]
        if journals:
            parts.append(_("Journals: %s", ', '.join(journals)))
        if options.get('all_entries'):
            parts.append(_("Including draft entries"))
        if options.get('partner_ids'):
            parts.append(_("Partners: %s", ', '.join(self.env['res.partner'].browse(options['partner_ids']).mapped('display_name'))))
        if options.get('analytic_account_ids'):
            parts.append(_("Analytic: %s", ', '.join(
                self.env['account.analytic.account'].browse(options['analytic_account_ids']).mapped('display_name'))))
        if options.get('account_ids'):
            parts.append(_("Accounts: %s", ', '.join(
                self.env['account.account'].browse(options['account_ids']).mapped('display_name'))))
        return ' · '.join(parts)

    def _ci_export_filename(self, options, extension):
        name = self._ci_get_title(options).replace(' ', '_').replace('/', '_')
        return f"{name}_{options['date']['date_to']}.{extension}"

    def export_to_pdf(self, options):
        options, lines = self._ci_export_data(options)
        report_ref = 'ci_account.action_ci_report_pdf_landscape' if self._ci_landscape \
            else 'ci_account.action_ci_report_pdf'
        data = {
            'title': self._ci_get_title(options),
            'company_name': ', '.join(self._ci_companies().mapped('name')),
            'filters': self._ci_filters_summary(options),
            'column_groups': self._ci_get_column_groups(options),
            'columns': self._ci_get_all_columns(options),
            'lines': lines,
        }
        pdf, _report_type = self.env['ir.actions.report']._render_qweb_pdf(report_ref, data={'ci_report': data})
        return pdf, self._ci_export_filename(options, 'pdf')

    def export_to_xlsx(self, options):
        if not xlsxwriter:
            raise UserError(self.env._("The Python library xlsxwriter is required for XLSX exports."))
        options, lines = self._ci_export_data(options)
        columns = self._ci_get_all_columns(options)
        column_groups = self._ci_get_column_groups(options)

        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True, 'strings_to_formulas': False})
        title = self._ci_get_title(options)
        sheet = workbook.add_worksheet(''.join(c for c in title if c not in '[]:*?/\\')[:31] or 'Report')
        title_fmt = workbook.add_format({'bold': True, 'font_size': 14})
        header_fmt = workbook.add_format({'bold': True, 'bottom': 1, 'align': 'center'})
        text_fmts = {}
        number_fmts = {}

        def text_fmt(level, bold):
            key = (level, bold)
            if key not in text_fmts:
                text_fmts[key] = workbook.add_format({'indent': level, 'bold': bold})
            return text_fmts[key]

        def number_fmt(figure, bold):
            key = (figure, bold)
            if key not in number_fmts:
                num_format = '0.0"%"' if figure == 'percentage' else '#,##0.00;-#,##0.00'
                number_fmts[key] = workbook.add_format({'num_format': num_format, 'bold': bold})
            return number_fmts[key]

        sheet.write(0, 0, title, title_fmt)
        sheet.write(1, 0, ', '.join(self._ci_companies().mapped('name')))
        sheet.write(2, 0, self._ci_filters_summary(options))
        row = 4
        if column_groups:
            col = 1
            for group in column_groups:
                if group['colspan'] > 1:
                    sheet.merge_range(row, col, row, col + group['colspan'] - 1, group['name'], header_fmt)
                else:
                    sheet.write(row, col, group['name'], header_fmt)
                col += group['colspan']
            row += 1
        sheet.write(row, 0, '', header_fmt)
        for col, column in enumerate(columns, start=1):
            sheet.write(row, col, column['name'], header_fmt)
        row += 1
        sheet.set_column(0, 0, 50)
        sheet.set_column(1, len(columns), 16)
        for line in lines:
            bold = bool(line.get('class'))
            sheet.write(row, 0, line['name'], text_fmt(min(int(line.get('level') or 0), 10), bold))
            for col, cell in enumerate(line['columns'], start=1):
                if cell['no_format'] is not None and cell['figure'] in ('monetary', 'percentage', 'float'):
                    sheet.write_number(row, col, cell['no_format'], number_fmt(cell['figure'], bold))
                elif cell['name']:
                    sheet.write(row, col, cell['name'], text_fmt(0, bold))
            row += 1
        workbook.close()
        return output.getvalue(), self._ci_export_filename(options, 'xlsx')
