{
    'name': 'Shop: Product Brand',
    'version': '19.0.1.0.0',
    'summary': "Shows the product's brand on its eCommerce page, under the rating, if the product says so",
    'description': """
On the eCommerce product page, the product's brand is shown under the
product rating (under the product name when ratings are off), and is given
to search engines in the page's structured data.

Each product has a "Display Brand on eCommerce" checkbox, next to its brand:
unticked, the brand stays assigned to the product but is not shown on the
website. "No Brand" is never shown.

Also adds a Brands menu to Website > eCommerce > Products and to
Sales > Configuration > Products.
""",
    'category': 'Website/Website',
    'author': 'EMI Platform',
    'license': 'LGPL-3',
    'depends': ['website_sale', 'product_brand'],
    'data': [
        'security/ir.model.access.csv',
        'views/product_template_views.xml',
        'views/menus.xml',
        'views/templates.xml',
    ],
    'auto_install': True,
    'installable': True,
}
