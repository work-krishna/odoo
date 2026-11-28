# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    'name': "NestSMS: Password Reset Codes by SMS",
    'version': '1.0',
    'category': 'Hidden/Tools',
    'summary': "Customers who forgot their password can get the reset code by SMS on their verified mobile "
               "number; a different code goes by email too, and either one works.",
    'depends': ['auth_signup_email_otp', 'sms_nestsms'],
    'data': [
        'views/res_config_settings_views.xml',
    ],
    # Does nothing until switched on in Settings.
    'auto_install': True,
    'author': "Krishna Kumar Sah",
    'license': 'LGPL-3',
}
