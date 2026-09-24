{
    'name': 'EMI Platform',
    'version': '19.0.1.0.0',
    'summary': 'Installs the whole EMI Platform: finance, marketplace, applications, accounting and Nepal IRD compliance',
    'description': """
EMI Platform
============
Meta-package: installing it installs every EMI Platform module and the
Nepal localization they are built for.

* emi_finance - finance companies, tenure plans, interest rates, down payments
* emi_marketplace - retailers, listings and moderation
* emi_application - online applications, KYC and the approval workflow
* emi_accounting - disbursement, installments, commission, retailer settlements
* emi_payment_np - customer portal and online payments
* payment_esewa / payment_khalti / payment_connectips / payment_fonepay - Nepali gateways
* l10n_np / l10n_np_ird - Nepal chart of accounts, VAT, BS calendar,
  fiscal-year numbering and IRD CBMS sync
""",
    'category': 'Accounting/Finance',
    'author': 'EMI Platform',
    'license': 'LGPL-3',
    'depends': [
        'emi_finance', 'emi_marketplace', 'emi_application', 'emi_accounting', 'emi_payment_np',
        'l10n_np_ird',
        'payment_esewa', 'payment_khalti', 'payment_connectips', 'payment_fonepay',
    ],
    'data': [],
    'installable': True,
    'application': True,
}
