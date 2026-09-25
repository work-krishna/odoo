# -*- coding: utf-8 -*-
from odoo import fields, models
from odoo.exceptions import AccessError, UserError


class ResCompany(models.Model):
    _inherit = 'res.company'

    emi_journal_id = fields.Many2one(
        'account.journal', string='EMI Journal', domain="[('type', '=', 'general'), ('company_id', '=', id)]",
        help="Miscellaneous journal for EMI disbursement, installment and settlement entries.",
    )
    # --- Marketplace company ---
    emi_vendor_clearing_account_id = fields.Many2one(
        'account.account', string='Collections Payable to Retailers',
        help="Marketplace: money collected (down payment + financing) on behalf of retailers "
             "until it is paid out in a vendor settlement.",
    )
    emi_commission_product_id = fields.Many2one(
        'product.product', string='Commission Product',
        help="Marketplace: service invoiced to retailers as the marketplace commission (with VAT).",
    )
    # --- Finance company ---
    emi_loan_account_id = fields.Many2one(
        'account.account', string='EMI Loans Receivable',
        help="Finance company: outstanding loan principal.",
    )
    emi_interest_income_account_id = fields.Many2one(
        'account.account', string='EMI Interest Income',
        help="Finance company: interest recognised on each installment (effective interest method).",
    )

    def _emi_free_code(self, prefix):
        self.ensure_one()
        Account = self.env['account.account'].with_company(self)
        code = int(prefix)
        while Account.search_count([('code', '=', str(code)), ('company_ids', 'in', self.id)]):
            code += 1
        return str(code)

    def _emi_create_account(self, prefix, name, account_type, reconcile=False):
        self.ensure_one()
        return self.env['account.account'].with_company(self).create({
            'code': self._emi_free_code(prefix),
            'name': name,
            'account_type': account_type,
            'reconcile': reconcile,
            'company_ids': [(6, 0, self.ids)],
        })

    def action_emi_setup_accounting(self):
        """Create whatever EMI journal, accounts and product this company
        is missing, depending on whether it is the marketplace or a lender."""
        if not self.env.su:
            if not self.env.user.has_group('account.group_account_manager'):
                raise AccessError("Only accounting administrators can set up EMI accounting.")
            if self - self.env.user.company_ids:
                raise AccessError("You can only set up EMI accounting for companies you have access to.")
        for company in self.sudo():
            # Work inside the target company: it is usually not among the
            # user's active companies (e.g. a lender company just created).
            company = company.with_company(company)
            Journal = company.env['account.journal']
            if not company.chart_template and not Journal.search_count([('company_id', '=', company.id)]):
                raise UserError(f"Install a chart of accounts for {company.name} first.")
            if not company.emi_journal_id:
                code = 'EMI'
                while Journal.search_count([('code', '=', code), ('company_id', '=', company.id)]):
                    code = code[:3] + str(len(code))
                company.emi_journal_id = Journal.create({
                    'name': 'EMI Operations', 'code': code, 'type': 'general', 'company_id': company.id,
                })
            if company.emi_is_marketplace:
                if not company.emi_vendor_clearing_account_id:
                    company.emi_vendor_clearing_account_id = company._emi_create_account(
                        '2150', 'EMI Collections Payable to Retailers', 'liability_current', reconcile=True,
                    )
                if not company.emi_commission_product_id:
                    company.emi_commission_product_id = company.env['product.product'].create({
                        'name': 'Marketplace Commission',
                        'type': 'service',
                        'sale_ok': True,
                        'purchase_ok': False,
                        'list_price': 0.0,
                        'company_id': company.id,
                        'taxes_id': [(6, 0, company.account_sale_tax_id.ids)],
                    })
            elif self.env['emi.finance.company'].sudo().search_count([('company_id', '=', company.id)]):
                if not company.emi_loan_account_id:
                    company.emi_loan_account_id = company._emi_create_account(
                        '1150', 'EMI Loans Receivable (Principal)', 'asset_current',
                    )
                if not company.emi_interest_income_account_id:
                    company.emi_interest_income_account_id = company._emi_create_account(
                        '4050', 'EMI Interest Income', 'income',
                    )
        return True

    def _emi_check_accounting(self, role):
        """Raise a clear error listing missing EMI accounting settings."""
        self.ensure_one()
        company = self.sudo()
        needed = {'emi_journal_id': 'EMI Journal'}
        if role == 'marketplace':
            needed.update({
                'emi_vendor_clearing_account_id': 'Collections Payable to Retailers',
                'emi_commission_product_id': 'Commission Product',
            })
        else:
            needed.update({
                'emi_loan_account_id': 'EMI Loans Receivable',
                'emi_interest_income_account_id': 'EMI Interest Income',
            })
        missing = [label for field, label in needed.items() if not company[field]]
        if missing:
            raise UserError(
                f"EMI accounting is not configured for {company.name}: {', '.join(missing)}. "
                "Open the company's EMI Accounting tab and click 'Set Up EMI Accounting'."
            )
