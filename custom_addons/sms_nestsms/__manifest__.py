# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    'name': "NestSMS",
    'version': '1.0',
    'category': 'Hidden/Tools',
    'summary': "Send every Odoo SMS through NestSMS, on Nepal's domestic routes only.",
    'description': " ",  # Non-empty string to avoid loading the README file.
    'depends': ['sms', 'phone_validation'],
    # Twilio routes SMS abroad, which NTA rules forbid for this account.
    'excludes': ['sms_twilio'],
    'data': [
        'security/ir.model.access.csv',
        'data/ir_cron_data.xml',
        'views/res_config_settings_views.xml',
        'views/sms_nestsms_otp_views.xml',
        'wizard/sms_nestsms_template_picker_views.xml',
        'wizard/sms_nestsms_test_views.xml',
    ],
    'author': "Krishna Kumar Sah",
    'license': 'LGPL-3',
}
