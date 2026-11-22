# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    'name': "Nepal Can Move Shipping",
    'version': '1.0',
    'category': 'Inventory/Delivery',
    'sequence': 300,
    'summary': "Ship, track and collect cash on delivery with Nepal Can Move (NCM).",
    'description': " ",  # Non-empty string to avoid loading the README file.
    'depends': ['stock_delivery'],
    'data': [
        'security/ir.model.access.csv',

        'data/delivery_ncm_data.xml',
        'data/ir_cron_data.xml',
        'data/mail_template_data.xml',

        'report/ncm_label_report.xml',

        'views/delivery_carrier_views.xml',
        'views/ncm_branch_views.xml',
        'views/ncm_log_views.xml',
        'views/portal_templates.xml',
        'views/product_warehouse_views.xml',
        'views/res_partner_views.xml',
        'views/stock_picking_views.xml',
        'wizard/ncm_comment_wizard_views.xml',
        'views/delivery_ncm_menus.xml',
    ],
    'post_init_hook': 'post_init_hook',
    'author': "Krishna Kumar Sah",
    'license': 'LGPL-3',
}
