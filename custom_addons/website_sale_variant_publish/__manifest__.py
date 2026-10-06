{
    'name': 'Shop: Publish Each Variant',
    'version': '19.0.1.0.0',
    'summary': 'Each variant of a product can be published or hidden on the website, from the list of variants',
    'description': """
Odoo publishes a whole product on the website, with all its variants: the
"Published" button of a variant publishes or hides its product, i.e. all the
variants of the product.

With this module, each variant also has its own "Published" switch, ticked by
default. It can be switched from the list of variants (Inventory > Products >
Product Variants), without opening the variants, and from the form of a
variant. A variant is on the website when both it and its product are
published.

On the website, a variant that is not published:

- can't be chosen on the product page: its attribute value is grayed out, or
  not shown at all when all the variants with this value are hidden (all the
  Red variants, ...). The product page opens on a published variant.
- can't be chosen in the window to choose the options of a product either.
- can't be added to the cart.

A product whose variants are all hidden is no longer listed in the shop.
In the backend, the variants that are not published can still be sold.
""",
    'category': 'Website/Website',
    'author': 'EMI Platform',
    'license': 'LGPL-3',
    'depends': ['website_sale', 'website_sale_variant_picker_fix'],
    'data': [
        'views/product_views.xml',
        'views/templates.xml',
    ],
    'assets': {
        'web.assets_tests': [
            'website_sale_variant_publish/static/tests/tours/**/*',
        ],
    },
    'installable': True,
}
