# -*- coding: utf-8 -*-
from collections import defaultdict

from odoo import fields, models
from odoo.tools import SQL

AGING_BUCKETS = 6  # at date, 1-30, 31-60, 61-90, 91-120, older


class CiAccountReportAged(models.AbstractModel):
    """Open receivable/payable items as of a date, by age.

    The amount still open at the report date is the balance of the item minus
    the reconciliations dated up to that date, so a report printed as of a past
    date ignores the payments received afterwards.
    """
    _name = 'ci.account.report.aged'
    _inherit = 'ci.account.report'
    _description = "Aged Partner Balance"

    _ci_date_mode = 'single'
    _ci_default_date_filter = 'today'
    _ci_filters = ('draft', 'unfold_all', 'partner', 'aging', 'hide_zero')
    _ci_landscape = True
    _ci_account_types = ('asset_receivable', 'liability_payable')
    _ci_sign = 1

    def _ci_get_columns(self, options):
        _ = self.env._
        return [
            {'name': _("Invoice Date"), 'figure': 'date'},
            {'name': _("Due Date"), 'figure': 'date'},
            {'name': _("At Date"), 'figure': 'monetary', 'blank_if_zero': True},
            {'name': _("1-30"), 'figure': 'monetary', 'blank_if_zero': True},
            {'name': _("31-60"), 'figure': 'monetary', 'blank_if_zero': True},
            {'name': _("61-90"), 'figure': 'monetary', 'blank_if_zero': True},
            {'name': _("91-120"), 'figure': 'monetary', 'blank_if_zero': True},
            {'name': _("Older"), 'figure': 'monetary', 'blank_if_zero': True},
            {'name': _("Total"), 'figure': 'monetary'},
        ]

    def _ci_open_items(self, options, partner_id=None):
        """``[(aml, residual_at_date, bucket_index)]`` of the open items."""
        date_to = fields.Date.to_date(options['date']['date_to'])
        domain = self._ci_base_domain(options) + [
            ('account_id.account_type', 'in', list(self._ci_account_types)),
            ('date', '<=', date_to),
        ]
        if partner_id is not None:
            domain.append(('partner_id', '=', partner_id or False))
        query = self.env['account.move.line']._search(domain)
        self.env.cr.execute(query.select(SQL(
            """
            account_move_line.id,
            account_move_line.balance
              - COALESCE((SELECT SUM(part.amount) FROM account_partial_reconcile part
                           WHERE part.debit_move_id = account_move_line.id AND part.max_date <= %(date)s), 0)
              + COALESCE((SELECT SUM(part.amount) FROM account_partial_reconcile part
                           WHERE part.credit_move_id = account_move_line.id AND part.max_date <= %(date)s), 0)
            """,
            date=date_to,
        )))
        rows = [(aml_id, residual) for aml_id, residual in self.env.cr.fetchall()]
        currency = self.env.company.currency_id
        rows = [(aml_id, residual) for aml_id, residual in rows if not currency.is_zero(residual)]
        amls = self.env['account.move.line'].browse([aml_id for aml_id, _residual in rows])
        by_invoice_date = options.get('aging_based_on') == 'invoice_date'
        result = []
        for aml, (_aml_id, residual) in zip(amls, rows):
            reference = (aml.move_id.invoice_date or aml.date) if by_invoice_date else (aml.date_maturity or aml.date)
            days = (date_to - reference).days
            if days <= 0:
                bucket = 0
            else:
                bucket = min((days - 1) // 30 + 1, AGING_BUCKETS - 1)
            result.append((aml, self._ci_sign * residual, bucket))
        return result

    def _ci_bucket_values(self, items):
        buckets = [0.0] * AGING_BUCKETS
        for _aml, residual, bucket in items:
            buckets[bucket] += residual
        return buckets + [sum(buckets)]

    def _ci_get_lines(self, options):
        _ = self.env._
        by_partner = defaultdict(list)
        for item in self._ci_open_items(options):
            by_partner[item[0].partner_id.id or False].append(item)
        partners = self.env['res.partner'].browse([pid for pid in by_partner if pid]).sorted(
            lambda p: (p.display_name or '').lower())
        lines = []
        totals = [0.0] * (AGING_BUCKETS + 1)
        for partner in list(partners) + ([None] if False in by_partner else []):
            items = by_partner[partner.id if partner else False]
            values = self._ci_bucket_values(items)
            totals = [a + b for a, b in zip(totals, values)]
            lines.append(self._ci_line(
                options, self._build_line_id(('partner', partner.id if partner else 0)),
                partner.display_name if partner else _("Unknown Partner"), [None, None] + values,
                unfoldable=True, lazy=True, actions=self._ci_line_actions('journal_items')))
        lines.append(self._ci_line(options, self._build_line_id(('total', 0)), _("Total"), [None, None] + totals,
                                   css='o_ci_total'))
        return lines

    def _ci_expand_line(self, options, line_id, offset=0, progress=None, limit=None):
        kind, value = self._parse_line_id(line_id)[-1]
        if kind != 'partner':
            return []
        lines = []
        items = sorted(self._ci_open_items(options, partner_id=int(value) or False),
                       key=lambda item: (item[0].date_maturity or item[0].date, item[0].id))
        for aml, residual, bucket in items:
            buckets = [0.0] * AGING_BUCKETS
            buckets[bucket] = residual
            lines.append(self._ci_line(
                options, f"{line_id}|aml-{aml.id}", aml.move_name or aml.move_id.display_name,
                [aml.move_id.invoice_date or aml.date, aml.date_maturity] + buckets + [residual],
                level=1, parent_id=line_id, hide_if_zero=False, actions=self._ci_line_actions('record')))
        return lines

    def _ci_get_line_domain(self, options, line_id):
        kind, value = self._parse_line_id(line_id)[-1]
        if kind == 'partner':
            items = self._ci_open_items(options, partner_id=int(value) or False)
            return [('id', 'in', [aml.id for aml, _residual, _bucket in items])]
        return None


class CiAccountReportAgedReceivable(models.AbstractModel):
    _name = 'ci.account.report.aged.receivable'
    _inherit = 'ci.account.report.aged'
    _description = "Aged Receivable"

    _ci_account_types = ('asset_receivable',)


class CiAccountReportAgedPayable(models.AbstractModel):
    _name = 'ci.account.report.aged.payable'
    _inherit = 'ci.account.report.aged'
    _description = "Aged Payable"

    _ci_account_types = ('liability_payable',)
    _ci_sign = -1
