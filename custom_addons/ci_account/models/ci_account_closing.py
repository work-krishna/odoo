# -*- coding: utf-8 -*-
from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    ci_tax_payable_account_id = fields.Many2one(
        'account.account', string="Tax Payable Account",
        help="Receives the tax due by a tax return closing entry when the tax group has no payable account.")
    ci_tax_receivable_account_id = fields.Many2one(
        'account.account', string="Tax Receivable Account",
        help="Receives the tax to recover by a tax return closing entry when the tax group has no receivable account.")
    ci_retained_earnings_account_id = fields.Many2one(
        'account.account', string="Retained Earnings Account",
        domain="[('account_type', '=', 'equity')]",
        help="Equity account the year-end earnings allocation moves the profit or loss to.")


class AccountMove(models.Model):
    _inherit = 'account.move'

    ci_tax_closing_date_from = fields.Date(string="Tax Closing From", readonly=True, copy=False)
    ci_tax_closing_date_to = fields.Date(string="Tax Closing To", readonly=True, copy=False, index=True)


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    ci_fiscalyear_last_day = fields.Integer(related='company_id.fiscalyear_last_day', readonly=False)
    ci_fiscalyear_last_month = fields.Selection(related='company_id.fiscalyear_last_month', readonly=False)
    ci_tax_payable_account_id = fields.Many2one(related='company_id.ci_tax_payable_account_id', readonly=False)
    ci_tax_receivable_account_id = fields.Many2one(related='company_id.ci_tax_receivable_account_id', readonly=False)
    ci_retained_earnings_account_id = fields.Many2one(
        related='company_id.ci_retained_earnings_account_id', readonly=False)
