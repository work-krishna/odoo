# Part of Odoo. See LICENSE file for full copyright and licensing details.
from dateutil.relativedelta import relativedelta

from odoo import Command, api, fields, models
from odoo.exceptions import UserError


class L10nNpVatReportWizard(models.TransientModel):
    _name = 'l10n.np.vat.report.wizard'
    _description = "Nepal VAT Report"

    # NOTE: This report is an internal reconciliation / filing-prep aid.
    # It is not an official or certified IRD form - actual filing still
    # goes through IRD's own portal/format.

    company_id = fields.Many2one(
        comodel_name='res.company',
        string="Company",
        required=True,
        default=lambda self: self.env.company,
    )
    currency_id = fields.Many2one(related='company_id.currency_id')
    date_from = fields.Date(string="From", required=True)
    date_to = fields.Date(string="To", required=True)
    vat_sale_tax_ids = fields.Many2many(
        comodel_name='account.tax',
        relation='l10n_np_vat_report_sale_tax_rel',
        column1='wizard_id',
        column2='tax_id',
        string="Output VAT Taxes",
        domain="[('company_id', '=', company_id), ('type_tax_use', '=', 'sale'),"
               " ('amount_type', '=', 'percent'), ('is_withholding_tax_on_payment', '=', False)]",
    )
    vat_purchase_tax_ids = fields.Many2many(
        comodel_name='account.tax',
        relation='l10n_np_vat_report_purchase_tax_rel',
        column1='wizard_id',
        column2='tax_id',
        string="Input VAT Taxes",
        domain="[('company_id', '=', company_id), ('type_tax_use', '=', 'purchase'),"
               " ('amount_type', '=', 'percent'), ('is_withholding_tax_on_payment', '=', False)]",
    )
    line_ids = fields.One2many(
        comodel_name='l10n.np.vat.report.wizard.line',
        inverse_name='wizard_id',
        string="Lines",
        compute='_compute_line_ids',
        store=True,
    )
    total_output_vat = fields.Monetary(compute='_compute_totals')
    total_input_vat = fields.Monetary(compute='_compute_totals')
    net_amount = fields.Monetary(
        compute='_compute_totals',
        help="Positive: Net VAT Payable to IRD. Negative: Net VAT Refundable / carried forward.",
    )

    @api.model
    def default_get(self, fields_list):
        vals = super().default_get(fields_list)
        if 'date_from' in fields_list or 'date_to' in fields_list:
            today = fields.Date.context_today(self)
            last_month_end = today.replace(day=1) - relativedelta(days=1)
            last_month_start = last_month_end.replace(day=1)
            vals.setdefault('date_from', last_month_start)
            vals.setdefault('date_to', last_month_end)
        return vals

    @api.onchange('company_id')
    def _onchange_company_id(self):
        for wizard in self:
            wizard.vat_sale_tax_ids = self.env['account.tax'].search([
                ('company_id', '=', wizard.company_id.id),
                ('type_tax_use', '=', 'sale'),
                ('amount_type', '=', 'percent'),
                ('is_withholding_tax_on_payment', '=', False),
            ])
            wizard.vat_purchase_tax_ids = self.env['account.tax'].search([
                ('company_id', '=', wizard.company_id.id),
                ('type_tax_use', '=', 'purchase'),
                ('amount_type', '=', 'percent'),
                ('is_withholding_tax_on_payment', '=', False),
            ])

    @api.depends('company_id', 'date_from', 'date_to', 'vat_sale_tax_ids', 'vat_purchase_tax_ids')
    def _compute_line_ids(self):
        MoveLine = self.env['account.move.line']
        for wizard in self:
            line_vals = []
            for tax_type, taxes in (('sale', wizard.vat_sale_tax_ids), ('purchase', wizard.vat_purchase_tax_ids)):
                if not taxes or not wizard.company_id or not wizard.date_from or not wizard.date_to:
                    continue
                domain = [
                    ('parent_state', '=', 'posted'),
                    ('company_id', '=', wizard.company_id.id),
                    ('date', '>=', wizard.date_from),
                    ('date', '<=', wizard.date_to),
                    ('tax_line_id', 'in', taxes.ids),
                ]
                groups = MoveLine._read_group(
                    domain,
                    groupby=['tax_line_id'],
                    aggregates=['tax_base_amount:sum', 'balance:sum'],
                )
                for tax, base_sum, balance_sum in groups:
                    line_vals.append(Command.create({
                        'tax_id': tax.id,
                        'tax_type': tax_type,
                        'base_amount': abs(base_sum or 0.0),
                        'tax_amount': abs(balance_sum or 0.0),
                    }))
            wizard.line_ids = line_vals

    @api.depends('line_ids.tax_type', 'line_ids.tax_amount')
    def _compute_totals(self):
        for wizard in self:
            wizard.total_output_vat = sum(wizard.line_ids.filtered(lambda l: l.tax_type == 'sale').mapped('tax_amount'))
            wizard.total_input_vat = sum(wizard.line_ids.filtered(lambda l: l.tax_type == 'purchase').mapped('tax_amount'))
            wizard.net_amount = wizard.total_output_vat - wizard.total_input_vat

    def action_print_pdf(self):
        self.ensure_one()
        return self.env.ref('l10n_np.action_report_l10n_np_vat_report').report_action(self)

    def action_export_xlsx(self):
        self.ensure_one()
        try:
            import xlsxwriter  # noqa: PLC0415
        except ImportError as exc:
            raise UserError(self.env._("The xlsxwriter Python library is required to export this report.")) from exc

        import io  # noqa: PLC0415

        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        bold = workbook.add_format({'bold': True})
        money = workbook.add_format({'num_format': '#,##0.00'})
        sheet = workbook.add_worksheet("Nepal VAT Report")

        sheet.write(0, 0, "Nepal VAT Report", bold)
        sheet.write(1, 0, "Company")
        sheet.write(1, 1, self.company_id.name)
        sheet.write(2, 0, "Period")
        sheet.write(2, 1, f"{self.date_from} to {self.date_to}")

        row = 4
        for title, tax_type in (("Output VAT (Sales)", 'sale'), ("Input VAT (Purchases)", 'purchase')):
            sheet.write(row, 0, title, bold)
            row += 1
            sheet.write_row(row, 0, ["Tax", "Taxable Value", "VAT Amount"], bold)
            row += 1
            lines = self.line_ids.filtered(lambda l, tax_type=tax_type: l.tax_type == tax_type)
            for line in lines:
                sheet.write(row, 0, line.tax_id.name)
                sheet.write(row, 1, line.base_amount, money)
                sheet.write(row, 2, line.tax_amount, money)
                row += 1
            row += 1

        sheet.write(row, 0, "Total Output VAT", bold)
        sheet.write(row, 2, self.total_output_vat, money)
        row += 1
        sheet.write(row, 0, "Total Input VAT", bold)
        sheet.write(row, 2, self.total_input_vat, money)
        row += 1
        sheet.write(row, 0, "Net VAT Payable / (Refundable)", bold)
        sheet.write(row, 2, self.net_amount, money)

        sheet.set_column(0, 0, 40)
        sheet.set_column(1, 2, 18)
        workbook.close()
        output.seek(0)

        attachment = self.env['ir.attachment'].create({
            'name': f"Nepal VAT Report - {self.date_from} to {self.date_to}.xlsx",
            'type': 'binary',
            'raw': output.read(),
            'res_model': self._name,
            'res_id': self.id,
        })
        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{attachment.id}?download=true',
            'target': 'self',
        }


class L10nNpVatReportWizardLine(models.TransientModel):
    _name = 'l10n.np.vat.report.wizard.line'
    _description = "Nepal VAT Report Line"

    wizard_id = fields.Many2one(comodel_name='l10n.np.vat.report.wizard', ondelete='cascade')
    currency_id = fields.Many2one(related='wizard_id.currency_id')
    tax_id = fields.Many2one(comodel_name='account.tax', string="Tax")
    tax_type = fields.Selection(
        selection=[('sale', "Output (Sales)"), ('purchase', "Input (Purchases)")],
        string="Type",
    )
    base_amount = fields.Monetary(string="Taxable Value")
    tax_amount = fields.Monetary(string="VAT Amount")
