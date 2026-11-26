# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    'name': "NestSMS: Nepal Can Move Delivery Updates",
    'version': '1.0',
    'category': 'Inventory/Delivery',
    'summary': "Text customers through NestSMS when Nepal Can Move sends their parcel out for delivery, and when it is delivered.",
    'depends': ['delivery_ncm', 'sms_nestsms'],
    'data': [
        'data/sms_template_data.xml',
        'views/delivery_carrier_views.xml',
    ],
    'auto_install': True,
    'author': "Krishna Kumar Sah",
    'license': 'LGPL-3',
}
