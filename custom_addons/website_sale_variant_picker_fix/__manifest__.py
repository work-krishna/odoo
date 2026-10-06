{
    'name': 'Shop: Variant Picker Fixes',
    'version': '19.0.1.0.0',
    'summary': "The product page grays out the variants that can't be chosen in every case",
    'description': """
On the product page, Odoo grays out the attribute values that lead to a variant
that can't be chosen (archived, and with other modules out of stock or not
published). Two cases where it doesn't:

- A product with a single attribute (only a Color, ...): the value is not
  grayed out, as Odoo grays it out "because of" the other values of the
  variant, of which there are none.
- When the id of the attribute value is the same number as the id of the
  product or of its variant: Odoo looks for the value's input in the whole
  product form and grays out the hidden product id instead. It also stops
  with an error when the value isn't on the page (not shown by another
  module).
""",
    'category': 'Website/Website',
    'author': 'EMI Platform',
    'license': 'LGPL-3',
    'depends': ['website_sale'],
    'assets': {
        'web.assets_frontend': [
            'website_sale_variant_picker_fix/static/src/interactions/**/*',
        ],
        'web.assets_tests': [
            'website_sale_variant_picker_fix/static/tests/tours/**/*',
        ],
    },
    'installable': True,
}
