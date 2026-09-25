{
    'name': 'EMI Accounting',
    'version': '19.0.1.1.0',
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
Payments ahead of schedule are held as the customer's advance and applied as
each installment falls due; early settlement bills the principal left plus
the interest accrued to date.

Retailer settlements: weekly / bi-weekly / monthly per retailer, netting the
collections against unpaid commission invoices.

EMI entries and receipts are undone only through Cancel Disbursement,
Reverse EMI Receipt and settlement Reverse, which keep the schedule and the
settlements consistent.
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
