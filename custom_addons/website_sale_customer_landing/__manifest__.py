{
    'name': 'Shop: Customers Land on the Store',
    'version': '19.0.1.0.0',
    'summary': 'Customers go to the homepage after signing in or signing up, and My Account gets a "Shop now" button',
    'description': """
Odoo sends customers to their account page (/my) after they sign in, sign up
or activate their account. With this module they land on the website's
homepage instead, ready to shop.

- A page that asked them to sign in still gets them back (for example the
  checkout).
- Employees still go to the backend.

My Account (/my/home) also gets a "Shop now" button that opens the shop.
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
