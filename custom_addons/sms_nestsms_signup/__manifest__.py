# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    'name': "NestSMS: Sign-up Activation Codes by SMS",
    'version': '1.1',
    'category': 'Hidden/Tools',
    'summary': "Website sign-ups also get an activation code by SMS (a different one from the email's); entering it proves the mobile number.",
    'depends': ['auth_signup_email_otp', 'sms_nestsms'],
    'data': [
        'views/res_config_settings_views.xml',
    ],
    # Does nothing until switched on in Settings.
    'auto_install': True,
    'author': "Krishna Kumar Sah",
    'license': 'LGPL-3',
}
