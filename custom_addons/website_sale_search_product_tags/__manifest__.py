{
    'name': 'Shop: Search Products by Tags',
    'version': '19.0.1.1.0',
    'summary': 'The website search also finds the products by their tags',
    'description': """
The search of the website finds the products by their name and internal
reference. With this module, it also finds them by their tags: searching
"Summer" finds the products tagged "Summer", even when "Summer" is not in
their name.

This works everywhere products are searched on the website: the search field
of the header and its suggestions, and the search of the shop.

- The tags of the variants count too: a product is found by the tags of any
  of its variants.
- The tags of the eCommerce categories count too, so a tag common to a whole
  category does not have to be added to each of its products: an eCommerce
  category has a Tags field (Website > eCommerce > Products > eCommerce
  Categories), and a product is found by the tags of its categories and of
  their parent categories.
- Only the tags that customers can see count (the "Visible to customers"
  switch of the tag): an internal tag never makes a product show up.
- A tag is found in any language of the website.
- When a search has a typo, the suggested correction ("Showing results for
  ...") can also be a tag.
""",
    'category': 'Website/Website',
    'author': 'EMI Platform',
    'license': 'LGPL-3',
    'depends': ['website_sale'],
    'data': [
        'views/product_public_category_views.xml',
    ],
    'installable': True,
}
