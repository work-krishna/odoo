{
    'name': 'Shop: Buy Now First',
    'version': '19.0.1.0.0',
    'summary': 'On the product page, "Buy now" takes the place and the look of "Add to cart", and the other way round',
    'description': """
With the "Buy now" button (Website > Editor > Product Page), the product page
shows "Add to cart" next to the quantity, filled with the main colour of the
website, and "Buy now" below it, outlined.

With this module, the two buttons are interchanged:

- "Buy now" is next to the quantity, filled with the main colour;
- "Add to cart" is below it, outlined.

They still do the same: "Buy now" adds the product to the cart and opens the
cart, "Add to cart" adds it and stays on the page. Without the "Buy now"
button, the product page doesn't change.
""",
    'category': 'Website/Website',
    'author': 'EMI Platform',
    'license': 'LGPL-3',
    'depends': ['website_sale'],
    'data': [
        'views/templates.xml',
    ],
    'assets': {
        'web.assets_tests': [
            'website_sale_buy_now_first/static/tests/tours/**/*',
        ],
    },
    'installable': True,
}
