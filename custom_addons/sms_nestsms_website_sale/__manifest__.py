# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    'name': "NestSMS: Verify the Mobile Number at Checkout",
    'version': '1.0',
    'category': 'Website/Website',
    'summary': "Shoppers confirm their mobile number with an SMS code before choosing delivery and paying.",
    'depends': ['website_sale', 'sms_nestsms'],
    'data': [
        'views/templates.xml',
        'views/res_config_settings_views.xml',
    ],
    # Does nothing until switched on in Settings.
    'auto_install': True,
    'author': "Krishna Kumar Sah",
    'license': 'LGPL-3',
}
