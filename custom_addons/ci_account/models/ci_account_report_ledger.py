# -*- coding: utf-8 -*-
from collections import defaultdict

from odoo import fields, models
from odoo.tools.misc import formatLang


class CiAccountReportTrialBalance(models.AbstractModel):
    _name = 'ci.account.report.trial.balance'
    _inherit = 'ci.account.report'
    _description = "Trial Balance"

    _ci_filters = ('journals', 'draft', 'hide_zero', 'hierarchy', 'analytic', 'unfold_all')
    _ci_landscape = True

    def _ci_get_column_groups(self, options):
        _ = self.env._
        return [
            {'name': _("Initial Balance"), 'colspan': 2},
            {'name': options['date']['string'], 'colspan': 2},
            {'name': _("End Balance"), 'colspan': 2},
        ]

    def _ci_get_columns(self, options):
        _ = self.env._
        return [{'name': _("Debit"), 'figure': 'monetary'}, {'name': _("Credit"), 'figure': 'monetary'}] * 3

    def _ci_get_lines(self, options):
        _ = self.env._
        date_from = fields.Date.to_date(options['date']['date_from'])
        date_to = fields.Date.to_date(options['date']['date_to'])
        initial, undistributed = self._ci_account_initial(options)
        period = self._ci_sum_by(
            options, self._ci_base_domain(options) + self._ci_date_domain(date_from, date_to), ['account_id'],
            date_to=date_to)

        account_ids = {key[0] for key in initial} | {key[0] for key in period}
        accounts = self.env['account.account'].browse(account_ids).sorted(lambda a: (a.code or '', a.name))
        rows = []
        for account in accounts:
            init = initial.get((account.id,), {}).get('balance', 0.0)
            moves = period.get((account.id,), {'debit': 0.0, 'credit': 0.0})
            rows.append((account, self._ci_tb_values(init, moves['debit'], moves['credit'])))

        lines = []
        if options.get('hierarchy'):
            lines += self._ci_hierarchy_lines(options, rows)
        else:
            for account, values in rows:
                lines.append(self._ci_line(options, self._build_line_id(('acc', account.id)),
                                           self._ci_account_name(account), values,
                                           actions=self._ci_line_actions('general_ledger', 'journal_items')))
        if not self.env.company.currency_id.is_zero(undistributed):
            values = self._ci_tb_values(undistributed, 0.0, 0.0)
            rows.append((None, values))
            lines.append(self._ci_line(options, self._build_line_id(('undistributed', 0)),
                                       _("Undistributed Profits/Losses"), values, hide_if_zero=False))
        totals = [sum(values[index] for _account, values in rows) for index in range(6)]
        lines.append(self._ci_line(options, self._build_line_id(('total', 0)), _("Total"), totals, css='o_ci_total'))
        return lines

    def _ci_tb_values(self, initial, debit, credit):
        end = initial + debit - credit
        return [max(initial, 0.0), max(-initial, 0.0), debit, credit, max(end, 0.0), max(-end, 0.0)]

    def _ci_hierarchy_lines(self, options, rows):
        """Group the account rows under their account groups (account.group)."""
        _ = self.env._

        def chain(account):
            groups = []
            group = account.group_id
            while group:
                groups.insert(0, group)
                group = group.parent_id
            return groups

        group_totals = defaultdict(lambda: [0.0] * 6)
        chains = {}
        for account, values in rows:
            chains[account.id] = chain(account)
            for group in chains[account.id] or [None]:
                key = group.id if group else 0
                group_totals[key] = [a + b for a, b in zip(group_totals[key], values)]

        lines, emitted = [], set()
        for account, values in rows:
            parent_id = None
            groups = chains[account.id]
            if not groups:
                if 0 not in emitted:
                    lines.append(self._ci_line(options, self._build_line_id(('grp', 0)), _("(No Group)"),
                                               group_totals[0], css='o_ci_group', unfoldable=True))
                    emitted.add(0)
                parent_id = self._build_line_id(('grp', 0))
            for depth, group in enumerate(groups):
                group_line_id = self._build_line_id(('grp', group.id))
                if group.id not in emitted:
                    name = f"{group.code_prefix_start} {group.name}" if group.code_prefix_start else group.name
                    lines.append(self._ci_line(options, group_line_id, name, group_totals[group.id], level=depth,
                                               parent_id=parent_id, css='o_ci_group', unfoldable=True))
                    emitted.add(group.id)
                parent_id = group_line_id
            lines.append(self._ci_line(options, self._build_line_id(('acc', account.id)),
                                       self._ci_account_name(account), values, level=max(len(groups), 1),
                                       parent_id=parent_id,
                                       actions=self._ci_line_actions('general_ledger', 'journal_items')))
        return lines

    def _ci_get_line_domain(self, options, line_id):
        kind, value = self._parse_line_id(line_id)[-1]
        if kind != 'acc':
            return None
        return self._ci_base_domain(options) + [('account_id', '=', int(value))] + self._ci_date_domain(
            options['date']['date_from'], options['date']['date_to'])


class CiAccountReportGeneralLedger(models.AbstractModel):
    _name = 'ci.account.report.general.ledger'
    _inherit = 'ci.account.report'
    _description = "General Ledger"

    _ci_filters = ('journals', 'draft', 'hide_zero', 'unfold_all', 'analytic', 'partner')
    _ci_landscape = True

    def _ci_get_columns(self, options):
        _ = self.env._
        return [
            {'name': _("Date"), 'figure': 'date'},
            {'name': _("Communication"), 'figure': 'string'},
            {'name': _("Partner"), 'figure': 'string'},
            {'name': _("Currency"), 'figure': 'string'},
            {'name': _("Debit"), 'figure': 'monetary', 'blank_if_zero': True},
            {'name': _("Credit"), 'figure': 'monetary', 'blank_if_zero': True},
            {'name': _("Balance"), 'figure': 'monetary'},
        ]

    def _ci_period_domain(self, options):
        return self._ci_base_domain(options) + self._ci_date_domain(
            options['date']['date_from'], options['date']['date_to'])

    def _ci_get_lines(self, options):
        _ = self.env._
        date_to = fields.Date.to_date(options['date']['date_to'])
        initial, undistributed = self._ci_account_initial(options)
        period = self._ci_sum_by(options, self._ci_period_domain(options), ['account_id'], date_to=date_to)
        account_ids = {key[0] for key in initial} | {key[0] for key in period}
        accounts = self.env['account.account'].browse(account_ids).sorted(lambda a: (a.code or '', a.name))
        lines = []
        total_debit = total_credit = total_balance = 0.0
        for account in accounts:
            init = initial.get((account.id,), {}).get('balance', 0.0)
            moves = period.get((account.id,), {'debit': 0.0, 'credit': 0.0, 'balance': 0.0})
            end = init + moves['balance']
            total_debit += moves['debit']
            total_credit += moves['credit']
            total_balance += end
            lines.append(self._ci_line(
                options, self._build_line_id(('acc', account.id)), self._ci_account_name(account),
                [None, None, None, None, moves['debit'], moves['credit'], end],
                unfoldable=True, lazy=True, actions=self._ci_line_actions('journal_items')))
        if not self.env.company.currency_id.is_zero(undistributed):
            total_balance += undistributed
            lines.append(self._ci_line(options, self._build_line_id(('undistributed', 0)),
                                       _("Undistributed Profits/Losses"),
                                       [None, None, None, None, None, None, undistributed], hide_if_zero=False))
        lines.append(self._ci_line(options, self._build_line_id(('total', 0)), _("Total"),
                                   [None, None, None, None, total_debit, total_credit, total_balance],
                                   css='o_ci_total'))
        return lines

    def _ci_expand_line(self, options, line_id, offset=0, progress=None, limit=None):
        _ = self.env._
        kind, value = self._parse_line_id(line_id)[-1]
        if kind != 'acc':
            return []
        account_id = int(value)
        lines = []
        if not offset:
            initial, _undistributed = self._ci_account_initial(options, account_id)
            progress = initial.get((account_id,), {}).get('balance', 0.0)
            lines.append(self._ci_line(
                options, f"{line_id}|initial-0", _("Initial Balance"),
                [None, None, None, None, None, None, progress], level=1, parent_id=line_id, hide_if_zero=False))
        progress = progress or 0.0
        domain = self._ci_period_domain(options) + [('account_id', '=', account_id)]
        amls = self.env['account.move.line'].search(
            domain, order='date, move_name, id', offset=offset, limit=limit + 1 if limit else None)
        has_more = bool(limit) and len(amls) > limit
        amls = amls[:limit] if limit else amls
        company_currency = self.env.company.currency_id
        for aml in amls:
            progress += aml.balance
            currency = ''
            if aml.currency_id and aml.currency_id != aml.company_currency_id:
                currency = formatLang(self.env, aml.amount_currency, currency_obj=aml.currency_id)
            lines.append(self._ci_line(
                options, f"{line_id}|aml-{aml.id}", aml.move_name or aml.move_id.display_name,
                [aml.date, aml.name or aml.ref or '', aml.partner_id.display_name or '', currency,
                 aml.balance > 0 and aml.balance or 0.0, aml.balance < 0 and -aml.balance or 0.0, progress],
                level=2, parent_id=line_id, hide_if_zero=False, actions=self._ci_line_actions('record')))
        if has_more:
            lines.append(self._ci_line(
                options, f"{line_id}|more-{offset + limit}", _("Load more..."), [], level=2, parent_id=line_id,
                hide_if_zero=False, extra={'load_more': {'offset': offset + limit, 'progress': progress}}))
        else:
            totals = self._ci_sum_by(options, domain, [], date_to=options['date']['date_to']).get(
                (), {'debit': 0.0, 'credit': 0.0})
            lines.append(self._ci_line(
                options, f"{line_id}|total-0", _("Total %s", self.env['account.account'].browse(account_id).display_name),
                [None, None, None, None, totals['debit'], totals['credit'], company_currency.round(progress)],
                level=1, parent_id=line_id, css='o_ci_subtotal'))
        return lines

    def _ci_get_line_domain(self, options, line_id):
        kind, value = self._parse_line_id(line_id)[-1]
        if kind == 'acc':
            return self._ci_period_domain(options) + [('account_id', '=', int(value))]
        return None


class CiAccountReportPartnerLedger(models.AbstractModel):
    _name = 'ci.account.report.partner.ledger'
    _inherit = 'ci.account.report'
    _description = "Partner Ledger"

    _ci_filters = ('journals', 'draft', 'hide_zero', 'unfold_all', 'partner', 'account_type', 'unreconciled')
    _ci_landscape = True

    def _ci_get_columns(self, options):
        _ = self.env._
        return [
            {'name': _("Date"), 'figure': 'date'},
            {'name': _("Journal"), 'figure': 'string'},
            {'name': _("Account"), 'figure': 'string'},
            {'name': _("Reference"), 'figure': 'string'},
            {'name': _("Due Date"), 'figure': 'date'},
            {'name': _("Debit"), 'figure': 'monetary', 'blank_if_zero': True},
            {'name': _("Credit"), 'figure': 'monetary', 'blank_if_zero': True},
            {'name': _("Balance"), 'figure': 'monetary'},
        ]

    def _ci_partner_domain(self, options):
        account_types = {
            'receivable': ['asset_receivable'],
            'payable': ['liability_payable'],
        }.get(options.get('account_type'), ['asset_receivable', 'liability_payable'])
        domain = self._ci_base_domain(options) + [('account_id.account_type', 'in', account_types)]
        if options.get('unreconciled'):
            domain.append(('reconciled', '=', False))
        return domain

    def _ci_get_lines(self, options):
        _ = self.env._
        date_from, date_to = options['date']['date_from'], options['date']['date_to']
        domain = self._ci_partner_domain(options)
        initial = self._ci_sum_by(options, domain + [('date', '<', date_from)], ['partner_id'], date_to=date_from)
        period = self._ci_sum_by(options, domain + self._ci_date_domain(date_from, date_to), ['partner_id'],
                                 date_to=date_to)
        partner_ids = {key[0] for key in initial} | {key[0] for key in period}
        partners = self.env['res.partner'].browse([pid for pid in partner_ids if pid]).sorted(
            lambda p: (p.display_name or '').lower())
        lines = []
        totals = [0.0, 0.0, 0.0]
        for partner in list(partners) + ([None] if False in partner_ids else []):
            key = (partner.id if partner else False,)
            init = initial.get(key, {}).get('balance', 0.0)
            moves = period.get(key, {'debit': 0.0, 'credit': 0.0, 'balance': 0.0})
            end = init + moves['balance']
            totals = [totals[0] + moves['debit'], totals[1] + moves['credit'], totals[2] + end]
            lines.append(self._ci_line(
                options, self._build_line_id(('partner', partner.id if partner else 0)),
                partner.display_name if partner else _("Unknown Partner"),
                [None] * 5 + [moves['debit'], moves['credit'], end],
                unfoldable=True, lazy=True, actions=self._ci_line_actions('journal_items')))
        lines.append(self._ci_line(options, self._build_line_id(('total', 0)), _("Total"), [None] * 5 + totals,
                                   css='o_ci_total'))
        return lines

    def _ci_partner_line_domain(self, options, partner_value):
        partner_id = int(partner_value) or False
        domain = [domain_part for domain_part in self._ci_partner_domain(options)]
        domain.append(('partner_id', '=', partner_id))
        return domain

    def _ci_expand_line(self, options, line_id, offset=0, progress=None, limit=None):
        _ = self.env._
        kind, value = self._parse_line_id(line_id)[-1]
        if kind != 'partner':
            return []
        date_from, date_to = options['date']['date_from'], options['date']['date_to']
        domain = self._ci_partner_line_domain(options, value)
        lines = []
        if not offset:
            progress = self._ci_sum_by(options, domain + [('date', '<', date_from)], [], date_to=date_from).get(
                (), {}).get('balance', 0.0)
            lines.append(self._ci_line(options, f"{line_id}|initial-0", _("Initial Balance"),
                                       [None] * 7 + [progress], level=1, parent_id=line_id, hide_if_zero=False))
        progress = progress or 0.0
        period_domain = domain + self._ci_date_domain(date_from, date_to)
        amls = self.env['account.move.line'].search(
            period_domain, order='date, move_name, id', offset=offset, limit=limit + 1 if limit else None)
        has_more = bool(limit) and len(amls) > limit
        amls = amls[:limit] if limit else amls
        for aml in amls:
            progress += aml.balance
            lines.append(self._ci_line(
                options, f"{line_id}|aml-{aml.id}", aml.move_name or aml.move_id.display_name,
                [aml.date, aml.journal_id.code, aml.account_id.code or aml.account_id.name,
                 aml.name or aml.ref or '', aml.date_maturity,
                 aml.balance > 0 and aml.balance or 0.0, aml.balance < 0 and -aml.balance or 0.0, progress],
                level=2, parent_id=line_id, hide_if_zero=False, actions=self._ci_line_actions('record')))
        if has_more:
            lines.append(self._ci_line(
                options, f"{line_id}|more-{offset + limit}", _("Load more..."), [], level=2, parent_id=line_id,
                hide_if_zero=False, extra={'load_more': {'offset': offset + limit, 'progress': progress}}))
        return lines

    def _ci_get_line_domain(self, options, line_id):
        kind, value = self._parse_line_id(line_id)[-1]
        if kind == 'partner':
            return self._ci_partner_line_domain(options, value) + self._ci_date_domain(
                options['date']['date_from'], options['date']['date_to'])
        return None


class CiAccountReportJournal(models.AbstractModel):
    _name = 'ci.account.report.journal'
    _inherit = 'ci.account.report'
    _description = "Journal Report"

    _ci_filters = ('journals', 'draft', 'unfold_all')
    _ci_landscape = True
    _ci_default_date_filter = 'this_month'
    _ci_moves_per_page = 100

    def _ci_get_columns(self, options):
        _ = self.env._
        return [
            {'name': _("Account"), 'figure': 'string'},
            {'name': _("Partner"), 'figure': 'string'},
            {'name': _("Label"), 'figure': 'string'},
            {'name': _("Debit"), 'figure': 'monetary', 'blank_if_zero': True},
            {'name': _("Credit"), 'figure': 'monetary', 'blank_if_zero': True},
        ]

    def _ci_period_domain(self, options):
        return self._ci_base_domain(options) + self._ci_date_domain(
            options['date']['date_from'], options['date']['date_to'])

    def _ci_get_lines(self, options):
        _ = self.env._
        groups = self._ci_sum_by(options, self._ci_period_domain(options), ['journal_id'],
                                 date_to=options['date']['date_to'])
        journals = self.env['account.journal'].browse([key[0] for key in groups]).sorted(
            lambda j: (j.company_id.id, j.sequence, j.code))
        lines = []
        for journal in journals:
            values = groups[(journal.id,)]
            name = f"{journal.name} ({journal.code})"
            if len(self._ci_companies()) > 1:
                name = f"{name} - {journal.company_id.name}"
            lines.append(self._ci_line(options, self._build_line_id(('journal', journal.id)), name,
                                       [None, None, None, values['debit'], values['credit']],
                                       css='o_ci_group', unfoldable=True, lazy=True,
                                       actions=self._ci_line_actions('journal_items')))
        return lines

    def _ci_expand_line(self, options, line_id, offset=0, progress=None, limit=None):
        _ = self.env._
        kind, value = self._parse_line_id(line_id)[-1]
        if kind != 'journal':
            return []
        domain = self._ci_period_domain(options) + [('journal_id', '=', int(value))]
        move_groups = self.env['account.move.line']._read_group(
            domain, ['move_id'], order='move_id')
        moves = self.env['account.move'].browse([move.id for (move,) in move_groups]).sorted(
            lambda m: (m.date, m.name or '', m.id))
        page_limit = self._ci_moves_per_page if limit else None
        page = moves[offset:offset + page_limit] if page_limit else moves[offset:]
        amls_by_move = defaultdict(lambda: self.env['account.move.line'])
        for aml in self.env['account.move.line'].search(domain + [('move_id', 'in', page.ids)], order='id'):
            amls_by_move[aml.move_id.id] |= aml
        lines = []
        for move in page:
            move_line_id = f"{line_id}|move-{move.id}"
            label = f"{move.name} · {fields.Date.to_string(move.date)}"
            if move.ref:
                label = f"{label} · {move.ref}"
            lines.append(self._ci_line(options, move_line_id, label, [], level=1, parent_id=line_id,
                                       css='o_ci_move', unfoldable=True, unfolded=True, hide_if_zero=False,
                                       actions=self._ci_line_actions('record')))
            for aml in amls_by_move[move.id]:
                lines.append(self._ci_line(
                    options, f"{move_line_id}|aml-{aml.id}", aml.account_id.code or '',
                    [aml.account_id.name, aml.partner_id.display_name or '', aml.name or '',
                     aml.debit, aml.credit],
                    level=2, parent_id=move_line_id, hide_if_zero=False))
        if page_limit and len(moves) > offset + page_limit:
            lines.append(self._ci_line(
                options, f"{line_id}|more-{offset + page_limit}", _("Load more..."), [], level=1, parent_id=line_id,
                hide_if_zero=False, extra={'load_more': {'offset': offset + page_limit}}))
        return lines

    def _ci_get_line_domain(self, options, line_id):
        kind, value = self._parse_line_id(line_id)[-1]
        if kind == 'journal':
            return self._ci_period_domain(options) + [('journal_id', '=', int(value))]
        if kind == 'move':
            return [('move_id', '=', int(value))]
        return None
