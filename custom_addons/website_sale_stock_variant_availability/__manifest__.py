{
    'name': 'Shop: Variant Availability',
    'version': '19.0.1.0.0',
    'summary': "The product page grays out the variants that are out of stock, and opens on one that is in stock",
    'description': """
Odoo already keeps the stock of each variant (Phone / Blue / 256 GB has its own
on hand quantity), and the shop already refuses to sell a variant that is out of
stock when the product is set not to sell out of stock: no Add to Cart for it,
and the cart and the checkout do not accept more than what is left.

With this module, the customer also sees it before choosing:

- On the product page, the options that would lead to an out-of-stock variant
  are grayed out (crossed out for colors), like the variants that do not exist.
  With Black and 256 GB selected, Red is grayed out when Red / 256 GB is out of
  stock, and 128 GB when Black / 128 GB is. It works with any number of
  attributes, and only grays out the exact combinations that are out of stock.
  Selecting one anyway shows Odoo's "Out of stock" message, without Add to Cart.
- The product page opens on the first variant that is in stock, instead of the
  first variant when that one is out of stock. A link to a given variant
  (?attribute_values=...) still opens that variant.
- In the shop, a product is only out of stock (no quick Add to Cart, "Out of
  stock" ribbon) when all its variants are, not as soon as its first one is.

Odoo grays out an option by looking for the input with its id in the whole
product form, which finds the hidden product (template) id first when it is
the same number: only the attribute values are looked at.

This only applies to products whose inventory is tracked, and which are not
allowed to be sold when out of stock: product form > Sales > "Sell when
Out-of-Stock" unticked (Website > Settings > Inventory Defaults > Out-of-Stock
"Continue Selling" is the default of new products).
""",
    'category': 'Website/Website',
    'author': 'EMI Platform',
    'license': 'LGPL-3',
    'depends': ['website_sale_stock'],
    'data': [
        'views/templates.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'website_sale_stock_variant_availability/static/src/interactions/**/*',
        ],
        'web.assets_tests': [
            'website_sale_stock_variant_availability/static/tests/tours/**/*',
        ],
    },
    'installable': True,
}
