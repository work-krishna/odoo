{
    'name': 'Shop: Variant Image Preview',
    'version': '19.0.1.0.0',
    'summary': "On the product page, hovering an attribute value shows the image of the variant it leads to",
    'description': """
Odoo already shows the images of the chosen variant on the product page: its
own image (Product > Variants > the variant > its image) and its Extra Variant
Media, then the product's Extra Product Media. A variant without its own image
shows the product's image.

With this module:

- Hovering an attribute value on the product page shows, in place of the
  displayed image, the image of the variant it leads to: the selected values
  with the hovered one instead. With Blue and 256 GB selected, hovering Red
  shows the image of Phone / Red / 256 GB. Moving away shows the image back,
  and clicking it keeps it, until Odoo shows the images of the new variant.
  Only a variant with its own image is previewed: hovering one that has none
  leaves the displayed image as it is. The images are known with the page,
  so hovering does not ask anything to the server. It works with colors,
  images, pills and radio buttons (not drop-down lists, whose options can't
  be hovered), and not on mobile, as Odoo's variant preview in the shop.
- An image given to one of the variants of a product is that variant's own,
  also when the product has no image yet: Odoo gives it to the product
  instead, i.e. to all its variants. It is then the product's image too, for
  the variants without their own image.
- The list of variants (Product > Variants) shows the image of each variant
  that has its own.
""",
    'category': 'Website/Website',
    'author': 'EMI Platform',
    'license': 'LGPL-3',
    'depends': ['website_sale'],
    'data': [
        'views/product_views.xml',
        'views/templates.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'website_sale_variant_image_preview/static/src/interactions/**/*',
        ],
        'web.assets_tests': [
            'website_sale_variant_image_preview/static/tests/tours/**/*',
        ],
    },
    'installable': True,
}
