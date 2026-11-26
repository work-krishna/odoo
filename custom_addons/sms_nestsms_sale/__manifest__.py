# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    'name': "NestSMS: Order Confirmation",
    'version': '1.0',
    'category': 'Sales/Sales',
    'summary': "Text customers through NestSMS when their order is confirmed.",
    'depends': ['sale', 'sms_nestsms'],
    'data': [
        'data/sms_template_data.xml',
        'views/res_config_settings_views.xml',
    ],
    'auto_install': True,
    'author': "Krishna Kumar Sah",
    'license': 'LGPL-3',
}
