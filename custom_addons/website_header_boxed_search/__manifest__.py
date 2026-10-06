{
    'name': 'Website: Search Field in the Rounded Box Menu',
    'version': '19.0.1.0.0',
    'summary': 'The "Rounded Box Menu" header shows a search field instead of a search icon',
    'description': """
The "Rounded Box Menu" header of the website only shows a search icon, which
opens a search window. With this module, it shows a search field instead,
right after the menu: the field takes all the space the menu leaves on the
menu bar, up to the icons on the right (cart, sign in, ...).

The menu keeps its room: when the menu bar is too narrow, the field shrinks
down to a minimum width, then the last menu items go into the "+" dropdown,
as before.

Nothing else changes: the field searches like the search window did, with
the suggestions shown while typing, and the "Search Bar" button of the
header's options in the website editor still shows or hides it. The other
headers, and the mobile menu, are unchanged.
""",
    'category': 'Website/Website',
    'author': 'EMI Platform',
    'license': 'LGPL-3',
    'depends': ['website'],
    'data': [
        'views/templates.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'website_header_boxed_search/static/src/scss/header.scss',
        ],
        'web.assets_tests': [
            'website_header_boxed_search/static/tests/tours/**/*',
        ],
    },
    'installable': True,
}
