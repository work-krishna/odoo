# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    'name': "Point of Sale Fonepay Direct QR",
    'version': '2.0',
    'category': 'Point of Sale',
    'summary': "Pay Point of Sale orders with Fonepay: shows Fonepay's own QR code directly on "
               "the POS screen and confirms automatically, no link to open on another phone.",
    'description': " ",  # Non-empty string to avoid loading the README file.
    'depends': ['point_of_sale', 'payment_fonepay'],
    'data': [],
    'assets': {
        'point_of_sale.assets_prod': [
            'pos_payment_fonepay/static/src/**/*',
        ],
    },
    'author': "Krishna Kumar Sah",
    'license': 'LGPL-3',
}
