# Part of Odoo. See LICENSE file for full copyright and licensing details.
from odoo import models
from odoo.addons.account.models.chart_template import template


class AccountChartTemplate(models.AbstractModel):
    _inherit = 'account.chart.template'

    @template('np')
    def _get_np_template_data(self):
        return {
            'property_account_receivable_id': 'l10n_np_1100',
            'property_account_payable_id': 'l10n_np_2000',
            'code_digits': '4',
        }

    @template('np', 'res.company')
    def _get_np_res_company(self):
        return {
            self.env.company.id: {
                'account_fiscal_country_id': 'base.np',
                'bank_account_code_prefix': '1020',
                'cash_account_code_prefix': '1000',
                'transfer_account_id': 'l10n_np_1050',
                'account_journal_suspense_account_id': 'l10n_np_1060',
                'default_cash_difference_income_account_id': 'l10n_np_4190',
                'default_cash_difference_expense_account_id': 'l10n_np_6990',
                'income_currency_exchange_account_id': 'l10n_np_4110',
                'expense_currency_exchange_account_id': 'l10n_np_6350',
                'account_journal_early_pay_discount_loss_account_id': 'l10n_np_6360',
                'account_journal_early_pay_discount_gain_account_id': 'l10n_np_4120',
                'account_sale_tax_id': 'vat_sale_13',
                'account_purchase_tax_id': 'vat_purchase_13',
                'income_account_id': 'l10n_np_4000',
                'expense_account_id': 'l10n_np_6100',
            },
        }
