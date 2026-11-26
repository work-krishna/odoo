# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    'name': "NestSMS: Sign-up Activation by SMS",
    'version': '1.0',
    'category': 'Hidden/Tools',
    'summary': "Website sign-ups get their activation code by SMS (approved NestSMS OTP template) instead of email.",
    'depends': ['auth_signup_email_otp', 'sms_nestsms'],
    'data': [
        'views/auth_signup_templates.xml',
        'views/res_config_settings_views.xml',
    ],
    # Does nothing until switched on in Settings.
    'auto_install': True,
    'author': "Krishna Kumar Sah",
    'license': 'LGPL-3',
}
