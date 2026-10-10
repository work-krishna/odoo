{
    'name': 'Shop: Product Page Opens on the First Media',
    'version': '19.0.1.0.0',
    'summary': "The product page first shows the first image or video of the product's media, then what the visitor picks",
    'description': """
The images of a product page are the image of the variant (or of the product),
its Extra Variant Media, then the Extra Product Media. Odoo first shows the
image of the variant.

With this module, the product page first shows the first of the media that
follow (image or video): the first Extra Variant Media of the variant, or else
the first Extra Product Media. Then it shows what the visitor picks:

- a thumbnail: that image or video;
- the previous / next arrows: the image or video before or after it, the
  image of the variant being just before;
- a variant: the images of that variant, from its image, as in Odoo.

A product without media shows its image, as in Odoo. Only the carousel layout
of the product page images changes (Website > Editor > Product Page > Images),
not the grid, which shows all the images at once.
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
            'website_sale_product_first_media/static/tests/tours/**/*',
        ],
    },
    'installable': True,
}
