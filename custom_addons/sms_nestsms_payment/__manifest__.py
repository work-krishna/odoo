# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    'name': "NestSMS: Payment Received",
    'version': '1.0',
    'category': 'Accounting/Accounting',
    'summary': "Text customers through NestSMS when their payment is received and confirmed.",
    'depends': ['account', 'sms_nestsms'],
    'data': [
        'data/sms_template_data.xml',
        'views/res_config_settings_views.xml',
    ],
    'auto_install': True,
    'author': "Krishna Kumar Sah",
    'license': 'LGPL-3',
}
