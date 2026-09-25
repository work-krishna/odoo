{
    'name': 'EMI Online Payments (Nepal)',
    'version': '19.0.1.1.0',
    'summary': 'Customers pay EMI down payments and installments online (eSewa, Khalti, connectIPS, Fonepay...)',
    'description': """
EMI Online Payments
===================
Customer portal for EMI loans plus online payment through any Odoo payment
provider enabled for the collecting company (payment_esewa, payment_khalti,
payment_connectips, payment_fonepay, ...):

* "My EMI Loans" portal pages with the installment schedule
* Pay the down payment (to the marketplace) or the next installment (to the
  finance company, or to the marketplace when it collects on its behalf)
* Completed payments are booked and reconciled against the installment
  schedule automatically, through the same logic as the backend wizards
""",
    'category': 'Accounting/Finance',
    'author': 'EMI Platform',
    'license': 'LGPL-3',
    'depends': ['emi_accounting', 'account_payment', 'portal'],
    'data': [
        'views/emi_portal_templates.xml',
    ],
    'installable': True,
}
