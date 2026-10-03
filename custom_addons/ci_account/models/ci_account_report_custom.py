# -*- coding: utf-8 -*-
import ast
import re
from collections import defaultdict
from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Domain
from odoo.tools.safe_eval import safe_eval

from odoo.addons.account.models.account_report import (
    ACCOUNT_CODES_ENGINE_SPLIT_REGEX,
    ACCOUNT_CODES_ENGINE_TERM_REGEX,
    CROSS_REPORT_REGEX,
)

# account.report.default_opening_date_filter -> ci_account date filters
DATE_FILTERS = {
    'this_year': 'this_year',
    'this_quarter': 'this_quarter',
    'this_month': 'this_month',
    'today': 'today',
    'previous_month': 'last_month',
    'previous_quarter': 'last_quarter',
    'previous_year': 'last_year',
    'this_return_period': 'this_month',
    'previous_return_period': 'last_month',
}
FIGURES = {
    'monetary': 'monetary',
    'percentage': 'percentage',
    'integer': 'float',
    'float': 'float',
    'date': 'date',
    'datetime': 'date',
}
AGGREGATION_TERM_REGEX = re.compile(r'(?<![\w.])([^().\s*/+\-]+)\.([^().\s*/+\-]+)')
BOUND_REGEX = re.compile(r'(if_above|if_below|if_between|if_other_expr_above|if_other_expr_below)\((.*)\)$')
NUMBER_REGEX = re.compile(r'[-+]?\d+(?:\.\d+)?')


class CiAccountReportCustom(models.AbstractModel):
    """Renders ``account.report`` records: the tax reports of the
    localizations and the statements users design themselves.

    Supported engines: ``account_codes`` (prefixes, ``\\(excluded)``, ``C``/``D``
    balance filters, ``tag(...)``), ``domain`` (``sum``, ``-sum``, ``sum_if_pos``,
    ``sum_if_neg``, ``count_rows``), ``tax_tags``, ``aggregation`` (line codes,
    ``sum_children``, ``if_above``/``if_below``/``if_between`` bounds,
    ``cross_report``) and ``external`` (manual values). ``custom`` expressions,
    which need Enterprise Python code, count as 0.
    """
    _name = 'ci.account.report.custom'
    _inherit = 'ci.account.report'
    _description = "Configurable Report"

    # -------------------------------------------------------------------------
    # REPORT DEFINITION
    # -------------------------------------------------------------------------

    def _ci_report(self, options):
        report_id = (options or {}).get('report_id') or self.env.context.get('report_id')
        report = self.env['account.report'].browse(int(report_id or 0)).exists()
        if not report:
            raise UserError(self.env._("This report does not exist anymore."))
        return report

    @api.model
    def _ci_get_options(self, previous=None):
        previous = dict(previous or {})
        previous['report_id'] = self._ci_report(previous).id
        options = super()._ci_get_options(previous)
        options['report_id'] = previous['report_id']
        return options

    def _ci_get_title(self, options):
        return self._ci_report(options).display_name

    def _ci_get_filters(self, options):
        report = self._ci_report(options)
        filters = ['draft', 'hide_zero', 'unfold_all']
        if report.filter_journals:
            filters.append('journals')
        if report.filter_period_comparison:
            filters.append('comparison')
        if report.filter_analytic:
            filters.append('analytic')
        if report.filter_partner:
            filters.append('partner')
        return tuple(filters)

    def _ci_get_date_mode(self, previous):
        return 'range' if self._ci_report(previous).filter_date_range else 'single'

    def _ci_get_default_date_filter(self, previous):
        report = self._ci_report(previous)
        return DATE_FILTERS.get(report.default_opening_date_filter) or 'this_year'

    def _ci_get_columns(self, options):
        report = self._ci_report(options)
        if not report.column_ids:
            return [{'name': self.env._("Balance"), 'figure': 'monetary', 'expression_label': 'balance'}]
        return [{
            'name': column.name,
            'figure': FIGURES.get(column.figure_type, 'string'),
            'blank_if_zero': column.blank_if_zero,
            'expression_label': column.expression_label,
        } for column in report.column_ids.sorted('sequence')]

    # -------------------------------------------------------------------------
    # LINES
    # -------------------------------------------------------------------------

    def _ci_get_lines(self, options):
        report = self._ci_report(options)
        periods = self._ci_get_periods(options)
        computed = [self._ci_compute_report(options, period, report) for period in periods]
        columns = self._ci_get_columns(options)
        lines = []
        roots = report.line_ids.filtered(lambda line: not line.parent_id).sorted('sequence')
        for line in roots:
            lines += self._ci_render_report_line(options, line, None, 0, computed, columns)
        return lines

    def _ci_render_report_line(self, options, report_line, parent_id, level, computed, columns):
        line_id = self._build_line_id(('rline', report_line.id))
        expressions = {expression.label: expression for expression in report_line.expression_ids}
        values = []
        for period_values in computed:
            for column in columns:
                expression = expressions.get(column['expression_label'])
                values.append(period_values['totals'].get(expression.id, 0.0) if expression else None)
        children = report_line.children_ids.sorted('sequence')
        groups = self._ci_line_groups(report_line, expressions, computed, columns)
        has_children = bool(children or groups)
        css = 'o_ci_section' if level == 0 and has_children else ('o_ci_group' if has_children else '')
        lines = [self._ci_line(
            options, line_id, report_line.name, values, level=report_line.hierarchy_level or level,
            parent_id=parent_id, css=css, unfoldable=has_children and report_line.foldable,
            hide_if_zero=report_line.hide_if_zero or not has_children,
            actions=self._ci_line_actions('journal_items') if self._ci_line_has_audit(report_line) else ())]
        for child in children:
            lines += self._ci_render_report_line(options, child, line_id, level + 1, computed, columns)
        for key, name, group_values in groups:
            lines.append(self._ci_line(
                options, f"{line_id}|grp-{key}", name, group_values, level=(report_line.hierarchy_level or level) + 1,
                parent_id=line_id,
                actions=self._ci_line_actions('journal_items') if report_line.groupby == 'account_id' else ()))
        return lines

    def _ci_line_groups(self, report_line, expressions, computed, columns):
        """Child lines of a line grouped by a field (``groupby``)."""
        if not report_line.groupby:
            return []
        keys = set()
        for period_values in computed:
            for expression in expressions.values():
                keys |= set(period_values['groups'].get(expression.id, {}))
        field_name = report_line.groupby.split(',')[0].strip()
        comodel = self.env['account.move.line']._fields[field_name].comodel_name \
            if field_name in self.env['account.move.line']._fields else None
        records = self.env[comodel].browse([key for key in keys if key]) if comodel else None
        names = {record.id: record.display_name for record in records} if records is not None else {}
        if comodel == 'account.account':
            names = {account.id: self._ci_account_name(account) for account in records}
        result = []
        for key in sorted(keys, key=lambda k: names.get(k, str(k)) or ''):
            values = []
            for period_values in computed:
                for column in columns:
                    expression = expressions.get(column['expression_label'])
                    values.append(period_values['groups'].get(expression.id, {}).get(key, 0.0) if expression else None)
            result.append((key or 0, names.get(key) or self.env._("(None)"), values))
        return result

    def _ci_line_has_audit(self, report_line):
        return any(expression.engine in ('domain', 'account_codes', 'tax_tags') for expression in report_line.expression_ids)

    # -------------------------------------------------------------------------
    # COMPUTATION
    # -------------------------------------------------------------------------

    def _ci_compute_report(self, options, period, report, _stack=None):
        """``{'totals': {expression_id: value}, 'groups': {expression_id: {key: value}}}``"""
        stack = (_stack or set()) | {report.id}
        totals, groups = {}, {}
        expressions = report.line_ids.expression_ids
        for expression in expressions:
            if expression.engine in ('domain', 'account_codes', 'tax_tags'):
                groupby = expression.report_line_id.groupby
                group_field = groupby.split(',')[0].strip() if groupby else None
                total, by_group = self._ci_compute_engine(options, period, expression, group_field)
                totals[expression.id] = total
                if group_field:
                    groups[expression.id] = by_group
            elif expression.engine == 'external':
                totals[expression.id] = self._ci_compute_external(options, period, expression)
            elif expression.engine == 'custom':
                totals[expression.id] = 0.0
        self._ci_compute_aggregations(options, period, report, expressions, totals, stack)
        return {'totals': totals, 'groups': groups}

    def _ci_scope_dates(self, scope, period):
        date_from, date_to = period['date_from'], period['date_to']
        fy_start = self._ci_fiscal_year_start(date_to)
        if scope == 'from_beginning':
            return None, date_to
        if scope == 'from_fiscalyear':
            return fy_start, date_to
        if scope == 'to_beginning_of_fiscalyear':
            return None, fy_start - timedelta(days=1)
        if scope == 'to_beginning_of_period':
            return None, date_from - timedelta(days=1)
        return date_from, date_to

    def _ci_expression_domain(self, options, period, expression):
        """Journal items an expression of the domain/account_codes/tax_tags engine
        sums, and how: ``(domain, sign, mode)``; mode is ``sum``, ``sum_if_pos``,
        ``sum_if_neg``, ``count_rows`` or ``per_account`` (account codes with a
        ``C``/``D`` balance filter, returned as a list of term domains)."""
        date_from, date_to = self._ci_scope_dates(expression.date_scope, period)
        base = Domain(self._ci_base_domain(options) + self._ci_date_domain(date_from, date_to))
        if expression.engine == 'domain':
            formula_domain = ast.literal_eval(expression.formula)
            subformula = (expression.subformula or 'sum').replace(' ', '')
            sign = -1 if subformula.startswith('-') else 1
            mode = subformula.lstrip('-')
            return base & Domain(formula_domain), sign, mode
        if expression.engine == 'tax_tags':
            country = expression.report_line_id.report_id.country_id
            tags = self.env['account.account.tag'].with_context(active_test=False).search(
                self.env['account.account.tag']._get_tax_tags_domain(expression.formula, country.id))
            sign = -1 if expression.formula.startswith('-') else 1
            domain = base & Domain('tax_tag_ids', 'in', tags.ids) \
                & self.env['account.move.line']._get_tax_exigible_domain()
            return domain, sign, 'sum'
        terms = []
        for token in ACCOUNT_CODES_ENGINE_SPLIT_REGEX.split(expression.formula.replace(' ', '')):
            if not token:
                continue
            match = ACCOUNT_CODES_ENGINE_TERM_REGEX.match(token)
            if not match:
                continue
            prefix = match['prefix']
            tag_match = re.match(r'^tag\((.+)\)$', prefix)
            if tag_match:
                tag_ref = tag_match.group(1)
                tag = self.env['account.account.tag'].browse(int(tag_ref)) if tag_ref.isdigit() \
                    else self.env.ref(tag_ref, raise_if_not_found=False)
                term_domain = Domain('account_id.tag_ids', 'in', tag.ids if tag else [])
            else:
                term_domain = Domain('account_id.code', '=like', f'{prefix}%')
            for excluded in filter(None, (match['excluded_prefixes'] or '').split(',')):
                term_domain &= Domain('account_id.code', 'not =like', f'{excluded}%')
            terms.append((base & term_domain, -1 if match['sign'] == '-' else 1, match['balance_character']))
        return terms, 1, 'account_codes'

    def _ci_compute_engine(self, options, period, expression, group_field=None):
        """Total of an expression and, when its line has a groupby, its value per group key."""
        Line = self.env['account.move.line']
        domain, sign, mode = self._ci_expression_domain(options, period, expression)
        by_group = defaultdict(float)
        group_fields = [group_field] if group_field else []
        if mode == 'account_codes':
            total = 0.0
            for term_domain, term_sign, balance_character in domain:
                fields_ = ['account_id'] + [f for f in group_fields if f != 'account_id']
                for row in Line._read_group(term_domain, fields_, ['balance:sum']):
                    *keys, balance = row
                    if balance_character == 'D' and balance <= 0 or balance_character == 'C' and balance >= 0:
                        continue
                    value = term_sign * balance
                    total += value
                    if group_field:
                        key = keys[0] if group_field == 'account_id' else keys[1]
                        by_group[key.id if isinstance(key, models.BaseModel) else key] += value
            return total, dict(by_group)
        if mode == 'count_rows':
            if group_field:
                for key, count in Line._read_group(domain, group_fields, ['__count']):
                    by_group[key.id if isinstance(key, models.BaseModel) else key] += count
            return float(Line.search_count(domain)), dict(by_group)
        rows = Line._read_group(domain, group_fields, ['balance:sum'])
        total = 0.0
        for row in rows:
            *keys, balance = row
            if mode == 'sum_if_pos' and balance <= 0 or mode == 'sum_if_neg' and balance >= 0:
                continue
            value = sign * balance
            total += value
            if group_field:
                key = keys[0]
                by_group[key.id if isinstance(key, models.BaseModel) else key] += value
        return total, dict(by_group)

    def _ci_compute_external(self, options, period, expression):
        date_from, date_to = self._ci_scope_dates(expression.date_scope, period)
        domain = [
            ('target_report_expression_id', '=', expression.id),
            ('company_id', 'in', self._ci_companies().ids),
            ('date', '<=', date_to),
        ]
        if date_from:
            domain.append(('date', '>=', date_from))
        values = self.env['account.report.external.value'].search(domain, order='date desc, id desc')
        if expression.formula == 'most_recent':
            latest = values[:1]
            return values.filtered(lambda v: v.date == latest.date) and sum(
                values.filtered(lambda v: v.date == latest.date).mapped('value')) or 0.0
        return sum(values.mapped('value'))

    def _ci_compute_aggregations(self, options, period, report, expressions, totals, stack):
        by_code = defaultdict(dict)
        for expression in report.line_ids.expression_ids:
            if expression.report_line_id.code:
                by_code[expression.report_line_id.code][expression.label] = expression
        pending = expressions.filtered(lambda e: e.engine == 'aggregation')
        cross_values = {}
        for _iteration in range(len(pending) + 1):
            progressed = False
            for expression in pending:
                if expression.id in totals:
                    continue
                value = self._ci_evaluate_aggregation(options, period, expression, totals, by_code, cross_values,
                                                      stack)
                if value is not None:
                    totals[expression.id] = value
                    progressed = True
            if not progressed:
                break
        for expression in pending:
            totals.setdefault(expression.id, 0.0)  # circular or unresolvable references

    def _ci_evaluate_aggregation(self, options, period, expression, totals, by_code, cross_values, stack):
        if expression.formula.strip() == 'sum_children':
            children = expression.report_line_id.children_ids.expression_ids.filtered(
                lambda e: e.label == expression.label)
            if any(child.id not in totals for child in children):
                return None
            return self._ci_apply_bounds(expression, sum(totals[child.id] for child in children), totals, by_code)

        codes = by_code
        subformula = (expression.subformula or '').strip()
        cross_match = CROSS_REPORT_REGEX.match(subformula)
        if cross_match:
            target = cross_match.group(1)
            other = self.env['account.report'].browse(int(target)) if target.isdigit() \
                else self.env.ref(target, raise_if_not_found=False)
            if not other or other.id in stack:
                return 0.0
            if other.id not in cross_values:
                computed = self._ci_compute_report(options, period, other, _stack=stack)
                other_codes = defaultdict(dict)
                for other_expression in other.line_ids.expression_ids:
                    if other_expression.report_line_id.code:
                        other_codes[other_expression.report_line_id.code][other_expression.label] = other_expression
                cross_values[other.id] = (computed['totals'], other_codes)
            source_totals, codes = cross_values[other.id]
        else:
            source_totals = totals

        unresolved = False

        def substitute(match):
            nonlocal unresolved
            target_expression = codes.get(match.group(1), {}).get(match.group(2))
            if not target_expression:
                return '0.0'
            if target_expression.id not in source_totals:
                unresolved = True
                return '0.0'
            return f'({source_totals[target_expression.id]!r})'

        formula = AGGREGATION_TERM_REGEX.sub(substitute, expression.formula)
        if unresolved:
            return None
        try:
            value = float(safe_eval(formula, {}))
        except ZeroDivisionError:
            value = 0.0
        except Exception:  # noqa: BLE001 - a broken user formula must not break the whole report
            value = 0.0
        if cross_match:
            return value
        return self._ci_apply_bounds(expression, value, totals, by_code)

    def _ci_apply_bounds(self, expression, value, totals, by_code):
        match = BOUND_REGEX.match((expression.subformula or '').replace(' ', ''))
        if not match:
            return value
        kind, args = match.groups()
        numbers = [float(number) for number in NUMBER_REGEX.findall(args)]
        if kind == 'if_above':
            return value if numbers and value > numbers[0] else 0.0
        if kind == 'if_below':
            return value if numbers and value < numbers[0] else 0.0
        if kind == 'if_between':
            return value if len(numbers) >= 2 and numbers[0] < value < numbers[1] else 0.0
        # if_other_expr_above(CODE.label, CUR(x)) / if_other_expr_below(...)
        other_match = AGGREGATION_TERM_REGEX.search(args)
        other = other_match and by_code.get(other_match.group(1), {}).get(other_match.group(2))
        other_value = totals.get(other.id, 0.0) if other else 0.0
        bound = float(NUMBER_REGEX.findall(args.split(',', 1)[-1])[0]) if ',' in args else 0.0
        if kind == 'if_other_expr_above':
            return value if other_value > bound else 0.0
        return value if other_value < bound else 0.0

    # -------------------------------------------------------------------------
    # DRILL-DOWN
    # -------------------------------------------------------------------------

    def _ci_get_line_domain(self, options, line_id):
        parsed = self._parse_line_id(line_id)
        rline = next((int(value) for kind, value in parsed if kind == 'rline'), None)
        if not rline:
            return None
        report_line = self.env['account.report.line'].browse(rline)
        period = self._ci_get_periods(options)[0]
        domains = []
        for expression in report_line.expression_ids.filtered(
                lambda e: e.engine in ('domain', 'account_codes', 'tax_tags')):
            domain, _sign, mode = self._ci_expression_domain(options, period, expression)
            if mode == 'account_codes':
                domains += [term_domain for term_domain, _term_sign, _character in domain]
            else:
                domains.append(domain)
        if not domains:
            return None
        domain = Domain.OR(domains)
        kind, value = parsed[-1]
        if kind == 'grp' and report_line.groupby:
            group_field = report_line.groupby.split(',')[0].strip()
            domain &= Domain(group_field, '=', int(value) or False)
        return list(domain)


class AccountReport(models.Model):
    _inherit = 'account.report'

    def action_ci_open_report(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.client',
            'name': self.display_name,
            'tag': 'ci_account_report',
            'context': {'report_model': 'ci.account.report.custom', 'report_id': self.id},
        }
