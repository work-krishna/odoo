# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    'name': "Point of Sale Fonepay Direct QR",
    'version': '1.0',
    'category': 'Point of Sale',
    'summary': "Show Fonepay's own QR code directly in Point of Sale, instead of a link the "
               "customer has to open on their own phone first.",
    'description': " ",  # Non-empty string to avoid loading the README file.
    'depends': ['point_of_sale', 'pos_online_payment', 'payment_fonepay'],
    'data': [],
    'assets': {
        'point_of_sale.assets_prod': [
            'pos_payment_fonepay/static/src/**/*',
        ],
    },
    'author': "Krishna Kumar Sah",
    'license': 'LGPL-3',
}
