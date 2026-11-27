# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    'name': "One-Time Codes",
    'version': '1.1',
    'category': 'Hidden/Tools',
    'summary': "One place that issues, delivers (email, SMS) and checks one-time codes for every flow.",
    'description': " ",  # Non-empty string to avoid loading the README file.
    'depends': ['mail'],
    'data': [
        'security/ir.model.access.csv',
        'data/mail_template_data.xml',
        'views/auth_otp_views.xml',
    ],
    'author': "Krishna Kumar Sah",
    'license': 'LGPL-3',
}
