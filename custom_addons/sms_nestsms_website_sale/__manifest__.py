# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    'name': "NestSMS: Verify the Mobile Number at Checkout",
    'version': '1.1',
    'category': 'Website/Website',
    'summary': "Buyers prove their own mobile number with an SMS code before they can order.",
    'depends': ['website_sale', 'sms_nestsms'],
    'data': [
        'views/templates.xml',
        'views/res_config_settings_views.xml',
        'views/sale_order_views.xml',
    ],
    # Does nothing until switched on in Settings; then it is strict.
    'auto_install': True,
    'author': "Krishna Kumar Sah",
    'license': 'LGPL-3',
}
