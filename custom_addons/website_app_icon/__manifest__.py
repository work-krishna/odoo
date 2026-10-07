{
    'name': 'Website App Icon',
    'version': '19.0.1.0.0',
    'summary': "The Odoo app installed from a website's domain has the website's name and its company's logo",
    'description': """
Odoo can be installed as an app (PWA) on phones and computers. Its name and
icon are the same everywhere: the "Web App Name" of the settings and Odoo's
icon. With this module, they follow the domain the app is installed from:

- the name is the name of the website of that domain;
- the icon is the logo of the company of that website, on a square of the
  colour around the logo, and follows the logo when it changes. A company
  without a logo of its own keeps Odoo's icon.

The same icon is used when adding Odoo to the home screen of an iPhone, and
on the page shown when the app is offline.

An app already installed keeps the icon it was installed with until the
phone updates it (Android does it on its own after a while, an iPhone never
does): remove the app and install it again to see the new icon at once.
""",
    'category': 'Website/Website',
    'author': 'EMI Platform',
    'license': 'LGPL-3',
    'depends': ['website'],
    'data': [
        'views/webclient_templates.xml',
    ],
    'installable': True,
}
