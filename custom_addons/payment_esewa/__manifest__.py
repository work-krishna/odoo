# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    'name': "Payment Provider: eSewa",
    'version': '1.1',
    'category': 'Accounting/Payment Providers',
    'sequence': 351,
    'summary': "A payment provider for eSewa ePay v2 (Nepal).",
    'description': " ",  # Non-empty string to avoid loading the README file.
    'depends': ['payment'],
    'data': [
        'views/payment_provider_views.xml',
        'views/payment_esewa_templates.xml',

        'data/payment_method_data.xml',
        'data/payment_provider_data.xml',  # Depends on payment_esewa_templates.xml & the method above.
        'data/payment_cron.xml',
    ],
    'post_init_hook': 'post_init_hook',
    'uninstall_hook': 'uninstall_hook',
    'author': "Krishna Kumar Sah",
    'license': 'LGPL-3',
}
