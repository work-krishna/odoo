# Part of Odoo. See LICENSE file for full copyright and licensing details.
from odoo import Command, fields
from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged('post_install_l10n', 'post_install', '-at_install')
class TestL10nNpLocalization(AccountTestInvoicingCommon):

    @classmethod
    @AccountTestInvoicingCommon.setup_country('np')
    def setUpClass(cls):
        super().setUpClass()
        cls.chart_template_env = cls.env['account.chart.template'].with_company(cls.company_data['company'])

    def test_chart_template_loaded(self):
        """ The Nepal chart template should create the key accounts, tax groups,
        taxes and fiscal positions this module relies on. """
        company = self.company_data['company']
        self.assertEqual(company.account_fiscal_country_id.code, 'NP')
        self.assertEqual(company.currency_id.name, 'NPR')

        receivable = self.chart_template_env.ref('l10n_np_1100')
        payable = self.chart_template_env.ref('l10n_np_2000')
        vat_output = self.chart_template_env.ref('l10n_np_2110')
        vat_input = self.chart_template_env.ref('l10n_np_1210')
        tds_payable = self.chart_template_env.ref('l10n_np_2130')
        self.assertEqual(receivable.account_type, 'asset_receivable')
        self.assertEqual(payable.account_type, 'liability_payable')
        self.assertTrue(vat_output)
        self.assertTrue(vat_input)
        self.assertTrue(tds_payable)

        vat_sale_13 = self.chart_template_env.ref('vat_sale_13')
        vat_purchase_13 = self.chart_template_env.ref('vat_purchase_13')
        tds_rent_10 = self.chart_template_env.ref('tds_rent_10')
        self.assertEqual(vat_sale_13.amount, 13)
        self.assertEqual(vat_purchase_13.amount, 13)
        self.assertEqual(tds_rent_10.amount, -10)
        self.assertTrue(tds_rent_10.is_withholding_tax_on_payment)

        domestic = self.chart_template_env.ref('fiscal_position_np_domestic')
        export = self.chart_template_env.ref('fiscal_position_np_export')
        self.assertEqual(domestic.country_id.code, 'NP')
        self.assertFalse(export.country_id)

    def test_tds_withheld_on_payment(self):
        """ A TDS tax attached to a vendor bill line should not affect the bill total,
        and should only be withheld when the payment is registered. """
        vat_purchase_13 = self.chart_template_env.ref('vat_purchase_13')
        tds_rent_10 = self.chart_template_env.ref('tds_rent_10')

        bill = self.env['account.move'].create({
            'move_type': 'in_invoice',
            'partner_id': self.partner_a.id,
            'invoice_date': '2026-07-15',
            'invoice_line_ids': [Command.create({
                'name': 'Office rent - July',
                'price_unit': 10000.0,
                'tax_ids': [Command.set((vat_purchase_13 + tds_rent_10).ids)],
            })],
        })
        bill.action_post()
        # VAT affects the total, the withholding tax does not.
        self.assertEqual(bill.amount_total, 11300.0)

        payment_register = self.env['account.payment.register']\
            .with_context(active_model='account.move', active_ids=bill.ids)\
            .create({})
        self.assertRecordValues(payment_register.withholding_line_ids, [{
            'tax_id': tds_rent_10.id,
            'base_amount': 10000.0,
            'amount': 1000.0,
        }])
        # Net payment = bill total - TDS withheld.
        self.assertEqual(payment_register.withholding_net_amount, 10300.0)

        payment = payment_register._create_payments()
        # `payment.amount` stays at the gross invoice total - the withholding
        # reduces the actual cash movement, not this field (matches core
        # l10n_account_withholding_tax test expectations).
        self.assertEqual(payment.amount, 11300.0)
        tds_payable = self.chart_template_env.ref('l10n_np_2130')
        tds_lines = payment.move_id.line_ids.filtered(lambda l: l.account_id == tds_payable)
        self.assertEqual(sum(tds_lines.mapped('balance')), -1000.0)
        # The liquidity/outstanding line should reflect the net cash actually paid
        # (negative: paying a vendor credits the outstanding/bank account).
        liquidity_lines = payment.move_id.line_ids.filtered(lambda l: l.account_id == payment.outstanding_account_id)
        self.assertEqual(sum(liquidity_lines.mapped('balance')), -10300.0)

    def test_vat_report_wizard(self):
        """ The VAT report wizard should aggregate Output/Input VAT for posted
        moves in the selected period. """
        vat_sale_13 = self.chart_template_env.ref('vat_sale_13')
        vat_purchase_13 = self.chart_template_env.ref('vat_purchase_13')

        invoice = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.partner_a.id,
            'invoice_date': '2026-07-10',
            'invoice_line_ids': [Command.create({
                'name': 'Consulting services',
                'price_unit': 20000.0,
                'tax_ids': [Command.set(vat_sale_13.ids)],
            })],
        })
        invoice.action_post()

        bill = self.env['account.move'].create({
            'move_type': 'in_invoice',
            'partner_id': self.partner_a.id,
            'invoice_date': '2026-07-12',
            'invoice_line_ids': [Command.create({
                'name': 'Office supplies',
                'price_unit': 5000.0,
                'tax_ids': [Command.set(vat_purchase_13.ids)],
            })],
        })
        bill.action_post()

        wizard = self.env['l10n.np.vat.report.wizard'].create({
            'company_id': self.company_data['company'].id,
            'date_from': fields.Date.from_string('2026-07-01'),
            'date_to': fields.Date.from_string('2026-07-31'),
            'vat_sale_tax_ids': [Command.set(vat_sale_13.ids)],
            'vat_purchase_tax_ids': [Command.set(vat_purchase_13.ids)],
        })

        self.assertEqual(wizard.total_output_vat, 2600.0)
        self.assertEqual(wizard.total_input_vat, 650.0)
        self.assertEqual(wizard.net_amount, 1950.0)

        # Smoke-test the report template actually renders (no QWeb errors).
        # Falls back to 'html' instead of 'pdf' when wkhtmltopdf isn't
        # installed on the machine running the test - that's an
        # environment limitation, not a module bug, so both are accepted.
        report_content, content_type = self.env['ir.actions.report']._render_qweb_pdf(
            'l10n_np.report_l10n_np_vat_report', wizard.ids)
        self.assertIn(content_type, ('pdf', 'html'))
        self.assertTrue(report_content)

        xlsx_action = wizard.action_export_xlsx()
        self.assertEqual(xlsx_action['type'], 'ir.actions.act_url')
