{
    'name': 'Shop: Compare Button Fit',
    'version': '19.0.1.0.0',
    'summary': 'On the product page, "Add to compare" shows only its icon when its name doesn\'t fit in the button',
    'description': """
With the large buttons of the product page (Website > Editor > Product Page),
"Add to compare" is one line high. On computers it only shows its icon, but
on tablets and phones it also shows its name, which wraps over several lines
and spills out of the button.

With this module, the name is shown next to the icon when it fits on the
button's line; otherwise only the icon is shown, centered in the button.
""",
    'category': 'Website/Website',
    'author': 'EMI Platform',
    'license': 'LGPL-3',
    'depends': ['website_sale_comparison'],
    'assets': {
        'web.assets_frontend': [
            'website_sale_compare_button_fit/static/src/scss/**/*',
        ],
        'web.assets_tests': [
            'website_sale_compare_button_fit/static/tests/tours/**/*',
        ],
    },
    'installable': True,
}
