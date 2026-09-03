# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    'name': "Fonepay Retry on Shop Confirmation",
    'version': '1.0',
    'category': 'Website/Website',
    'summary': "Show Fonepay's Retry/Cancel payment actions on the e-commerce order "
               "confirmation page (/shop/confirmation).",
    'description': " ",  # Non-empty string to avoid loading the README file.
    'depends': ['website_sale', 'payment_fonepay'],
    'data': [
        'views/payment_confirmation_status_templates.xml',
    ],
    'author': "Krishna Kumar Sah",
    'license': 'LGPL-3',
}
