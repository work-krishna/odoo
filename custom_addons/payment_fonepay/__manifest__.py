# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    'name': "Payment Provider: Fonepay",
    'version': '1.0',
    'category': 'Accounting/Payment Providers',
    'sequence': 350,
    'summary': "A payment provider for Fonepay Dynamic QR (Nepal).",
    'description': " ",  # Non-empty string to avoid loading the README file.
    'depends': ['payment'],
    'data': [
        'views/payment_provider_views.xml',
        'views/payment_fonepay_templates.xml',

        'data/payment_method_data.xml',
        'data/payment_provider_data.xml',  # Depends on payment_fonepay_templates.xml & the method above.
    ],
    'assets': {
        'web.assets_frontend': [
            'payment_fonepay/static/src/interactions/**/*',
        ],
    },
    'post_init_hook': 'post_init_hook',
    'uninstall_hook': 'uninstall_hook',
    'external_dependencies': {
        'python': ['qrcode'],
    },
    'images': ['static/description/icon.png'],
    'author': "Krishna Kumar Sah",
    'license': 'LGPL-3',
}
