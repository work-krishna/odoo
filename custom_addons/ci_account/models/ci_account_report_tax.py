# -*- coding: utf-8 -*-
from collections import defaultdict

from odoo import fields, models
from odoo.fields import Domain


class CiAccountReportTax(models.AbstractModel):
    """Generic tax report: base and tax amounts of each tax, sales then purchases.

    Only tax-exigible journal items count (cash basis taxes enter the report
    once paid), as in the Enterprise generic tax report.
    """
    _name = 'ci.account.report.tax'
    _inherit = 'ci.account.report'
    _description = "Tax Report"

    _ci_filters = ('comparison', 'journals', 'draft', 'hide_zero')
    _ci_default_date_filter = 'last_month'

    def _ci_get_columns(self, options):
        _ = self.env._
        return [{'name': _("Net"), 'figure': 'monetary'}, {'name': _("Tax"), 'figure': 'monetary'}]

    def _ci_period_domain(self, options, period):
        domain = self._ci_base_domain(options) + self._ci_date_domain(period['date_from'], period['date_to'])
        return Domain.AND([domain, self.env['account.move.line']._get_tax_exigible_domain()])

    def _ci_period_amounts(self, options, period):
        """``{tax_id: [net, tax]}`` in the report sign (sales and purchases positive)."""
        Line = self.env['account.move.line']
        domain = self._ci_period_domain(options, period)
        amounts = defaultdict(lambda: [0.0, 0.0])
        for tax, balance in Line._read_group(domain & Domain('tax_line_id', '!=', False),
                                             ['tax_line_id'], ['balance:sum']):
            amounts[tax.id][1] += balance
        for tax, balance in Line._read_group(domain & Domain('tax_ids', '!=', False), ['tax_ids'], ['balance:sum']):
            # a group of taxes reports its base on each of its children
            targets = tax.children_tax_ids if tax.amount_type == 'group' else tax
            for target in targets:
                amounts[target.id][0] += balance
        taxes = self.env['account.tax'].with_context(active_test=False).browse(list(amounts))
        for tax in taxes:
            sign = -1 if tax.type_tax_use == 'sale' else 1
            amounts[tax.id] = [sign * value for value in amounts[tax.id]]
        return amounts

    def _ci_get_lines(self, options):
        _ = self.env._
        periods = self._ci_get_periods(options)
        amounts = [self._ci_period_amounts(options, period) for period in periods]
        tax_ids = {tax_id for period_amounts in amounts for tax_id in period_amounts}
        taxes = self.env['account.tax'].with_context(active_test=False).browse(tax_ids).sorted(
            lambda t: (t.sequence, t.name))
        sections = [
            ('sale', _("Sales")),
            ('purchase', _("Purchases")),
            ('none', _("Other Taxes")),
        ]
        lines = []
        section_tax_totals = {}
        for type_tax_use, label in sections:
            section_taxes = taxes.filtered(lambda t: t.type_tax_use == type_tax_use)
            if not section_taxes:
                continue
            section_id = self._build_line_id(('section', type_tax_use))
            totals = []
            for period_amounts in amounts:
                net = sum(period_amounts.get(tax.id, [0.0, 0.0])[0] for tax in section_taxes)
                tax_amount = sum(period_amounts.get(tax.id, [0.0, 0.0])[1] for tax in section_taxes)
                totals += [net, tax_amount]
            section_tax_totals[type_tax_use] = totals[1::2]
            lines.append(self._ci_line(options, section_id, label, totals, css='o_ci_section',
                                       actions=self._ci_line_actions('journal_items')))
            for tax in section_taxes:
                values = []
                for period_amounts in amounts:
                    values += period_amounts.get(tax.id, [0.0, 0.0])
                name = tax.name if len(self._ci_companies()) == 1 else f"{tax.name} ({tax.company_id.name})"
                lines.append(self._ci_line(options, self._build_line_id(('tax', tax.id)), name, values, level=1,
                                           parent_id=section_id, actions=self._ci_line_actions('journal_items')))
        if section_tax_totals:
            sales = section_tax_totals.get('sale', [0.0] * len(periods))
            purchases = section_tax_totals.get('purchase', [0.0] * len(periods))
            values = []
            for sale_tax, purchase_tax in zip(sales, purchases):
                values += [None, sale_tax - purchase_tax]
            lines.append(self._ci_line(options, self._build_line_id(('total', 0)),
                                       _("Tax Payable (Sales - Purchases)"), values, css='o_ci_total'))
        return lines

    def _ci_get_line_domain(self, options, line_id):
        kind, value = self._parse_line_id(line_id)[-1]
        period = self._ci_get_periods(options)[0]
        domain = self._ci_period_domain(options, period)
        if kind == 'tax':
            tax = self.env['account.tax'].browse(int(value))
            return list(domain & (Domain('tax_line_id', '=', tax.id) | Domain('tax_ids', 'in', tax.ids)))
        if kind == 'section':
            return list(domain & (Domain('tax_line_id.type_tax_use', '=', value)
                                  | Domain('tax_ids.type_tax_use', '=', value)))
        return None

    def _ci_country_tax_reports(self):
        """Tax reports of the localization (account.report variants of the generic tax report)."""
        generic = self.env.ref('account.generic_tax_report', raise_if_not_found=False)
        if not generic:
            return self.env['account.report']
        return self.env['account.report'].search([
            ('root_report_id', '=', generic.id),
            ('country_id', '=', self.env.company.account_fiscal_country_id.id),
        ])

    def _ci_get_buttons(self, options):
        buttons = []
        if self._ci_country_tax_reports():
            buttons.append({'name': self.env._("Country Tax Report"), 'method': 'action_ci_country_tax_report'})
        if self.env.user.has_group('account.group_account_manager'):
            buttons.append({'name': self.env._("Closing Entry"), 'method': 'action_ci_tax_closing'})
        return buttons

    def action_ci_country_tax_report(self, options):
        reports = self._ci_country_tax_reports()
        if len(reports) == 1:
            action = reports.action_ci_open_report()
            action['context']['ci_report_options'] = {'date': options.get('date')}
            return action
        action = self.env['ir.actions.actions']._for_xml_id('ci_account.action_ci_account_report_custom')
        action['domain'] = [('id', 'in', reports.ids)]
        action['context'] = {}
        return action

    def action_ci_tax_closing(self, options):
        options = self._ci_get_options(options)
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._("Tax Return Closing"),
            'res_model': 'ci.account.tax.closing.wizard',
            'views': [(False, 'form')],
            'target': 'new',
            'context': {
                'default_date_from': options['date']['date_from'],
                'default_date_to': options['date']['date_to'],
            },
        }
