# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    'name': "Payment Provider: Khalti",
    'version': '1.0',
    'category': 'Accounting/Payment Providers',
    'sequence': 352,
    'summary': "A payment provider for Khalti ePayment (Nepal).",
    'description': " ",  # Non-empty string to avoid loading the README file.
    'depends': ['payment'],
    'data': [
        'views/payment_provider_views.xml',
        'views/payment_khalti_templates.xml',

        'data/payment_method_data.xml',
        'data/payment_provider_data.xml',  # Depends on payment_khalti_templates.xml & the method above.
        'data/payment_cron.xml',
    ],
    'post_init_hook': 'post_init_hook',
    'uninstall_hook': 'uninstall_hook',
    'author': "Krishna Kumar Sah",
    'license': 'LGPL-3',
}
