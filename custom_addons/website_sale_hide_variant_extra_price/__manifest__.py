{
    'name': 'Shop: No Extra Price Next to Variants',
    'version': '19.0.1.0.0',
    'summary': 'The attribute values of a product no longer show their extra price ("+ 5,000.00") on the website',
    'description': """
On the website, the attribute values of a product (12GB/256GB, Blue, ...) are
shown without the badge of their extra price ("+ 5,000.00 Rs"): on the product
page, and in the window to choose the options of a product (from the shop or
the optional products).

Only the display changes: the extra prices of the attribute values still apply,
the price shown on the product page is still the one of the selected variant,
and the cart and the orders keep the right prices. The configurator of the
sales orders, in the backend, still shows the extra prices.
""",
    'category': 'Website/Website',
    'author': 'EMI Platform',
    'license': 'LGPL-3',
    'depends': ['website_sale'],
    'data': [
        'views/templates.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'website_sale_hide_variant_extra_price/static/src/js/**/*',
        ],
        'web.assets_tests': [
            'website_sale_hide_variant_extra_price/static/tests/tours/**/*',
        ],
    },
    'installable': True,
}
