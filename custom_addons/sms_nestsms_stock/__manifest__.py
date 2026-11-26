# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    'name': "NestSMS: Shipping Confirmation",
    'version': '1.0',
    'category': 'Inventory/Inventory',
    'summary': "Send Inventory's 'order shipped' SMS through NestSMS, in plain short wording.",
    'depends': ['stock_sms', 'sms_nestsms'],
    'data': [
        'data/sms_template_data.xml',
        'views/res_config_settings_views.xml',
    ],
    'post_init_hook': 'post_init_hook',
    'uninstall_hook': 'uninstall_hook',
    'auto_install': True,
    'author': "Krishna Kumar Sah",
    'license': 'LGPL-3',
}
