{
    'name': 'Shop: Two-Line Product Names',
    'version': '19.0.1.0.0',
    'summary': "Product names in the /shop listing take at most two lines",
    'description': """
In the /shop product listing (grid and list layouts), a product name longer
than two lines is cut off with an ellipsis; hovering it shows the full name.
The product page and the product carousels are not affected.
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
            'website_sale_product_name_clamp/static/src/scss/product_name.scss',
        ],
    },
    'installable': True,
}
