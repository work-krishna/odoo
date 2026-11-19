# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    'name': "Nepal Can Move: eCommerce",
    'version': '1.0',
    'category': 'Website/Website',
    'summary': "Customers pick their NCM delivery area or collection branch at checkout.",
    'description': " ",  # Non-empty string to avoid loading the README file.
    'depends': ['website_sale', 'delivery_ncm'],
    'data': [
        'views/address_templates.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'website_sale_ncm/static/src/interactions/*.js',
        ],
        'web.assets_tests': [
            'website_sale_ncm/static/tests/tours/*.js',
        ],
    },
    'auto_install': True,
    'author': "Krishna Kumar Sah",
    'license': 'LGPL-3',
}
