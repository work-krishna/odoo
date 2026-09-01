# Part of Odoo. See LICENSE file for full copyright and licensing details.
{
    'name': 'Nepal - Accounting',
    'version': '19.0.1.0.0',
    'icon': '/account/static/description/l10n.png',
    'countries': ['np'],
    'category': 'Accounting/Localizations/Account Charts',
    'summary': 'Nepal fiscal localization: Chart of Accounts, VAT, TDS, VAT report',
    'description': """
Nepal - Accounting
===================

Provides a Nepal-specific fiscal localization:

- Chart of Accounts sized for a general Nepali business
- VAT (13% standard rate) sale/purchase tax templates and a 0% / exempt
  category
- Domestic and Export fiscal positions
- TDS (Tax Deducted at Source) withholding taxes on vendor payments, built
  on Odoo's native withholding-tax-on-payment engine
- A "Nepal VAT Report" wizard (PDF/XLSX) summarizing Output VAT, Input VAT
  and the resulting Net Payable / Refundable position, to help prepare an
  IRD VAT filing

IMPORTANT: The chart of accounts, VAT rate and TDS rates included here are
based on publicly documented Nepal tax rules and are provided as a v1
starting point ONLY. They are NOT an official or certified IRD format.
Verify all rates and account structure against the current Finance Act and
IRD notifications - and consult a qualified Nepali accountant - before any
production use.
""",
    'author': 'Krishna Kumar Sah',
    'maintainer': 'Krishna Kumar Sah',
    'license': 'LGPL-3',
    'depends': [
        'account',
        'base_vat',
        'l10n_account_withholding_tax',
    ],
    'data': [
        'data/ir_sequence_data.xml',
        'security/ir.model.access.csv',
        'wizard/l10n_np_vat_report_wizard_views.xml',
        'report/l10n_np_vat_report_actions.xml',
        'report/l10n_np_vat_report_templates.xml',
    ],
    'auto_install': ['account'],
    'installable': True,
    'application': False,
}
