{
    'name': 'EMI Finance',
    'version': '19.0.1.0.0',
    'summary': 'Finance company setup, tenure plans, interest rates and down payment options for EMI purchases',
    'description': """
EMI Finance
===========
Foundational configuration module for the EMI Platform.

* Finance companies (each linked 1:1 to a separate Odoo company)
* Tenure plans (e.g. 6 / 9 / 12 / 18 / 24 months) as editable master data
* Interest rate configuration per finance company / tenure plan,
  supporting both flat-rate and reducing-balance calculation methods,
  with effective date ranges
* Down payment options per product, with a configurable minimum
  (percentage or fixed amount); customers may pay more than the minimum
""",
    'category': 'Accounting/Finance',
    'author': 'EMI Platform',
    'license': 'LGPL-3',
    'depends': ['base', 'product'],
    'data': [
        'security/finance_security.xml',
        'security/ir.model.access.csv',
        'data/tenure_plan_data.xml',
        'views/tenure_plan_views.xml',
        'views/finance_company_views.xml',
        'views/interest_rate_views.xml',
        'views/downpayment_option_views.xml',
        'views/menu_views.xml',
    ],
    'installable': True,
    'application': True,
}
