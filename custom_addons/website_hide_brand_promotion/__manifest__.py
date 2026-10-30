{
    'name': 'Website: Hide "Powered by Odoo"',
    'version': '19.0.1.0.0',
    'summary': 'The footer of the website no longer promotes Odoo ("Powered by Odoo - The #1 Open Source eCommerce")',
    'description': """
The copyright bar at the bottom of every page of the website (shop, cart,
portal, login...) shows, next to the copyright, a promotion of Odoo:
"Powered by Odoo", followed by "Create a free website" or, with the shop,
"The #1 Open Source eCommerce".

With this module, the copyright bar only shows the copyright.
""",
    'category': 'Website/Website',
    'author': 'EMI Platform',
    'license': 'LGPL-3',
    'depends': ['website'],
    'data': [
        'views/website_templates.xml',
    ],
    'installable': True,
}
