{
    'name': 'Shop: VAT-Inclusive Order Total',
    'version': '19.0.1.0.0',
    'summary': 'The order summary shows the total with "Incl. VAT" under it instead of Subtotal and Taxes lines',
    'description': """
When a website displays its prices tax included (Website > Configuration >
Settings > eCommerce > Display Product Prices: Tax Included), the order
summary of the cart, checkout, payment and confirmation pages no longer lists
a Subtotal and a Taxes line. It shows the Total, with a smaller "Incl. VAT"
under it when that total really includes tax. An order without any tax
(untaxed or 0% products, or a fiscal position that removes the tax) shows the
Total alone. Changing the delivery method updates the note.

Only the display changes: the order's untaxed amount, taxes and total are
computed and recorded as before, and the order PDF, the customer portal and
invoices keep their tax breakdown.

A website that displays prices tax excluded keeps the Subtotal / Taxes / Total
breakdown, since its customers were shown prices before tax.
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
            'website_sale_vat_included_total/static/src/interactions/**/*',
        ],
        'web.assets_tests': [
            'website_sale_vat_included_total/static/tests/tours/**/*',
        ],
    },
    'installable': True,
}
