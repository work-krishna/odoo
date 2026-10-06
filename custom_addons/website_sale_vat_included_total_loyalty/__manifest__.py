{
    'name': 'Shop: VAT-Inclusive Order Total - Vouchers',
    'version': '19.0.1.0.0',
    'summary': "Vouchers, gift cards and free shipping get rows of their own in the VAT-inclusive order summary",
    'description': """
In the VAT-inclusive order summary of Shop: VAT-Inclusive Order Total, each
discount (a voucher, promo code, coupon, gift card or eWallet) and free
shipping is a row of its own between the Delivery Fee and the Total, as a
negative amount tax included, instead of a line among the items. The Items
Total no longer counts them, so that the rows still add up to the Total.
Free products stay among the items.

Installs itself with Shop: VAT-Inclusive Order Total and eCommerce Loyalty.
""",
    'category': 'Website/Website',
    'author': 'EMI Platform',
    'license': 'LGPL-3',
    'depends': ['website_sale_vat_included_total', 'website_sale_loyalty'],
    'auto_install': True,
    'installable': True,
}
