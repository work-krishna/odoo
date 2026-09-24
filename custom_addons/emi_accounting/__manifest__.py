{
    'name': 'EMI Accounting',
    'version': '19.0.1.0.0',
    'summary': 'Double-entry accounting for EMI loans: disbursement, installments, commissions and retailer settlements',
    'description': """
EMI Accounting
==============
Posts the books for every EMI loan, in the marketplace company and in the
finance company, using the standard Odoo accounting engine (so manual and
automated entries share the same ledgers and reports).

Disbursement (by the finance company's reviewer):

* Finance company: Dr EMI Loans Receivable (customer) / Cr payable to the
  marketplace for the financed amount
* Marketplace, acting as the retailer's agent: Dr customer (down payment),
  Dr finance company (financed amount) / Cr Collections Payable to Retailers
  (full price)
* Commission invoice from the marketplace to the retailer (with VAT; sent to
  IRD CBMS when l10n_np_ird is installed and enabled)
* Installment schedule: equal EMIs; principal/interest split by the
  effective interest method for both flat and reducing-balance loans

Installments: posted on their due date (Dr customer / Cr loan principal,
Cr interest income) and settled by payments registered by the finance
company, or collected by the marketplace and remitted, per finance company.

Retailer settlements: weekly / bi-weekly / monthly per retailer, netting the
collections against unpaid commission invoices.
""",
    'category': 'Accounting/Finance',
    'author': 'EMI Platform',
    'license': 'LGPL-3',
    'depends': ['account', 'emi_application'],
    'data': [
        'security/emi_accounting_security.xml',
        'security/ir.model.access.csv',
        'data/emi_accounting_data.xml',
        'wizard/payment_wizard_views.xml',
        'views/application_views.xml',
        'views/settlement_views.xml',
        'views/config_views.xml',
    ],
    'installable': True,
}
