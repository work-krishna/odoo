{
    'name': 'Shop: Product Brand',
    'version': '19.0.1.1.0',
    'summary': "Shows the product's brand on its eCommerce page, and filters the shop on brands",
    'description': """
On the eCommerce product page, "Brand: Apple" is shown under the product
rating (under the product name when ratings are off), and is given to search
engines in the page's structured data. "Apple" links to the shop showing
only Apple products.

In the shop, a Brand filter comes first among the attribute filters (in the
sidebar and in the mobile filters): check one or more brands to only see
their products. It keeps working with the categories, the attribute filters
and the search, and "Clear Filters" clears it too. It lists the brands of
the products found, and is not shown when they have less than two brands.

Each product has a "Display Brand on eCommerce" checkbox, next to its brand:
unticked, the brand stays assigned to the product but is not shown on the
website, and the brand filter does not find the product. "No Brand" is never
shown.

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
    'assets': {
        'web.assets_frontend': [
            'website_sale_product_brand/static/src/interactions/**/*',
        ],
        'web.assets_tests': [
            'website_sale_product_brand/static/tests/tours/**/*',
        ],
    },
    'auto_install': True,
    'installable': True,
}
