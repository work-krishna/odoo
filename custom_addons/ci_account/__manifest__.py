{
    'name': 'CI Accounting',
    'version': '19.0.1.0.0',
    'category': 'Accounting/Accounting',
    'summary': 'Full accounting for Odoo Community: financial reports, bank reconciliation, '
               'assets, deferrals, budgets, follow-ups, fiscal years, lock dates and closing',
    'description': """
CI Accounting
=============
One accounting app for every Chaitanya Innovation module. It turns the
Community "Invoicing" app into a full "Accounting" app:

* Access: Invoicing, Auditor (read-only), Accountant and Administrator roles
* Chart of accounts, account groups, tags, opening balances
* Financial reports with drill-down, comparison periods and PDF/XLSX export:
  Balance Sheet, Profit and Loss, Cash Flow Statement, Trial Balance,
  General Ledger, Partner Ledger, Aged Receivable/Payable, Tax Report,
  Journal Report
* Bank reconciliation: match bank transactions with invoices, bills and
  payments, write-offs, reconciliation models, auto-reconcile
* Fixed assets, deferred revenues and deferred expenses with depreciation boards
* Budgets (budget vs actual)
* Customer follow-ups (payment reminders)
* Fiscal years, lock dates, tax return closing entries, year-end earnings allocation
""",
    'author': 'Chaitanya Innovation',
    'license': 'LGPL-3',
    'depends': ['account'],
    'external_dependencies': {'python': ['xlsxwriter']},
    'data': [
        'security/ci_account_security.xml',
        'security/ir.model.access.csv',
        'security/ci_account_closing_security.xml',
        'views/ci_account_menus.xml',
        'report/ci_account_report_pdf.xml',
        'views/ci_account_closing_views.xml',
        'views/ci_account_report_views.xml',
        'views/ci_account_report_custom_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'ci_account/static/src/**/*',
        ],
        'web.assets_tests': [
            'ci_account/static/tests/tours/**/*',
        ],
    },
    'post_init_hook': '_ci_account_post_init',
    'uninstall_hook': '_ci_account_uninstall',
    'application': True,
    'installable': True,
}
