{
    'name': 'Shop: Categories Arrows',
    'version': '19.0.1.0.0',
    'summary': 'Small previous / next arrows on both sides of the categories shown at the top of the shop, when they overflow',
    'description': """
The shop can show its categories at the top of the products (Website >
Editor > Shop > Categories: Top). When they don't all fit, the others are
hidden on the right, and can only be reached by scrolling, dragging or swiping
them: a visitor may not know they're there.

With this module, when the categories don't all fit, a small arrow on each
side of them shows that there are more, and scrolls to them when clicked:

- the left arrow shows when categories are hidden on the left;
- the right arrow shows when categories are hidden on the right.

The arrows have no background, so as not to hide the categories. When all
the categories fit, there are no arrows, as without the module.
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
            'website_sale_categories_arrows/static/src/interactions/**/*',
            'website_sale_categories_arrows/static/src/scss/**/*',
        ],
        'web.assets_tests': [
            'website_sale_categories_arrows/static/tests/tours/**/*',
        ],
    },
    'installable': True,
}
