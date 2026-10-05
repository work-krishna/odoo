{
    'name': 'Shop: Product Description Below the Details',
    'version': '19.0.1.0.0',
    'summary': "On the product page, the description comes after the images, variants and Add to Cart, above the reviews",
    'description': """
On the product page, the product's eCommerce description is no longer shown
in the right-hand column under the product name. It gets its own full-width
"Description" section below the product details (images, price, variants,
Add to Cart / Buy Now, ...), above the alternative products and the customer
reviews.

A product without a description shows no such section; in the website editor
the empty section stays visible so a description can be typed in.
""",
    'category': 'Website/Website',
    'author': 'EMI Platform',
    'license': 'LGPL-3',
    'depends': ['website_sale'],
    'data': [
        'views/templates.xml',
    ],
    'installable': True,
}
