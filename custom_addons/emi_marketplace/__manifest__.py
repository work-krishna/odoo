{
    'name': 'EMI Marketplace',
    'version': '19.0.1.2.0',
    'summary': 'Multi-vendor phone marketplace: vendor onboarding, product ownership and listing moderation',
    'description': """
EMI Marketplace
===============
Multi-vendor layer for the EMI Platform's phone-only e-commerce catalog.

* Vendor onboarding with manual approval (auto-approval can be added later
  by extending the state machine / adding an automated transition)
* Each product is owned by a vendor and goes through a listing
  moderation workflow before it is published
* Vendor settlement frequency is configurable per vendor (weekly,
  bi-weekly or monthly) -- actual settlement runs are implemented in
  emi_accounting, which depends on this module
* Vendor users are portal users scoped to their own products and
  settlement statements
""",
    'category': 'Sales',
    'author': 'EMI Platform',
    'license': 'LGPL-3',
    'depends': ['base', 'product', 'portal', 'mail', 'emi_finance'],
    'data': [
        'security/marketplace_security.xml',
        'security/ir.model.access.csv',
        'views/vendor_views.xml',
        'views/phone_brand_views.xml',
        'views/product_template_views.xml',
        'views/menu_views.xml',
    ],
    'installable': True,
    'application': True,
}
