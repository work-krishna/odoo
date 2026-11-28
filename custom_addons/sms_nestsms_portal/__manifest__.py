# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    'name': "NestSMS: Verified Email and Mobile on My Account",
    'version': '1.0',
    'category': 'Hidden/Tools',
    'summary': "My Account shows whether the email address and the mobile number are verified, with a "
               "Verify button for each; the mobile number is verified with an SMS code.",
    'depends': ['portal', 'auth_signup_email_otp', 'sms_nestsms'],
    'data': [
        'views/templates.xml',
        'views/res_config_settings_views.xml',
    ],
    'auto_install': True,
    'author': "Krishna Kumar Sah",
    'license': 'LGPL-3',
}
