# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    'name': "NestSMS: Sign-up Activation Codes by SMS",
    'version': '1.0',
    'category': 'Hidden/Tools',
    'summary': "Website sign-ups also get their activation code by SMS: the same code as the email, from auth_otp.",
    'depends': ['auth_signup_email_otp', 'sms_nestsms'],
    'data': [
        'views/res_config_settings_views.xml',
    ],
    # Does nothing until switched on in Settings.
    'auto_install': True,
    'author': "Krishna Kumar Sah",
    'license': 'LGPL-3',
}
