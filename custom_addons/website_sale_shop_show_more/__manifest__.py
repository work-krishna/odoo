{
    'name': 'Shop: Show More Instead of Pages',
    'version': '19.0.1.0.0',
    'summary': 'The shop shows full rows of products and a "Show more" button instead of page numbers',
    'description': """
The number of products shown at once on the shop follows the number of
columns of the grid, so that the last row is always full:

- 5 columns: 50 products
- 4 columns: 48 products
- 3 columns: 48 products
- 2 columns: 40 products

The number is set when choosing the columns in the website editor (Shop page >
Size ... by [columns]). It can still be changed by hand afterwards, until the
columns are changed again.

Below the products, a "Show more" button replaces the page numbers: it adds
the next products to the grid, without leaving the page, and disappears with
the last products. Coming back to the shop (browser's back button, refresh)
shows the products that were already loaded again, at the same place on the
page.

Filters, sorting and search apply to the products that are added, as they did
to the pages.
""",
    'category': 'Website/Website',
    'author': 'EMI Platform',
    'license': 'LGPL-3',
    'depends': ['website_sale'],
    'data': [
        'views/templates.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'website_sale_shop_show_more/static/src/interactions/**/*',
        ],
        'web.assets_tests': [
            'website_sale_shop_show_more/static/tests/tours/**/*',
        ],
    },
    'post_init_hook': 'post_init_hook',
    'installable': True,
}
