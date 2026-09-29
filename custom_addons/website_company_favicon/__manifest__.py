{
    'name': 'Website Favicon from Company Logo',
    'version': '19.0.1.0.0',
    'summary': "Each website's favicon is its company's logo, and nothing when the company has no logo",
    'description': """
The favicon of every website is the logo of the company the website belongs
to, fitted into a square icon, and follows it when the logo changes. When
that company has no logo of its own (none, or Odoo's placeholder), the
website shows no favicon at all instead of Odoo's icon.
""",
    'category': 'Website/Website',
    'author': 'EMI Platform',
    'license': 'LGPL-3',
    'depends': ['website'],
    'data': [
        'views/website_templates.xml',
        'views/res_config_settings_views.xml',
    ],
    'post_init_hook': '_post_init_hook',
    'installable': True,
}
