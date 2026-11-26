# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    'name': "NestSMS: Log In with an SMS Code",
    'version': '1.0',
    'category': 'Hidden/Tools',
    'summary': "Customers log in to the website with a code texted to their verified mobile number.",
    'depends': ['portal', 'sms_nestsms'],
    'data': [
        'views/login_templates.xml',
        'views/res_config_settings_views.xml',
    ],
    # Does nothing until switched on in Settings.
    'auto_install': True,
    'author': "Krishna Kumar Sah",
    'license': 'LGPL-3',
}
