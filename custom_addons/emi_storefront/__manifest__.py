{
    'name': 'EMI Storefront',
    'version': '19.0.1.4.0',
    'summary': 'Public phone catalog with EMI calculator, online EMI applications with KYC, retailer dashboard',
    'description': """
EMI Storefront
==============
Custom website storefront for the EMI Platform (built on `website`, not
`website_sale`: the EMI application is the order).

* /phones - catalog of published phones from approved retailers, with brand,
  retailer, price and text filters and the lowest monthly EMI
* /phones/<phone> - specifications, variants and a live EMI calculator per
  finance company and tenure
* /phones/<phone>/apply - online EMI application with KYC details and
  document uploads, submitted for review
* /retailer/register - retailer self-registration with KYB documents
* /my/retailer - retailer dashboard: listings, applications for their
  phones and settlements
""",
    'category': 'Website',
    'author': 'EMI Platform',
    'license': 'LGPL-3',
    'depends': ['website', 'emi_payment_np', 'emi_marketplace'],
    'data': [
        'data/website_menu_data.xml',
        'views/catalog_templates.xml',
        'views/apply_templates.xml',
        'views/retailer_templates.xml',
    ],
    'installable': True,
    'application': True,
}
