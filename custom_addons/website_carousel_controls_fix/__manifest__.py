{
    'name': 'Website: Carousel Arrows Fix',
    'version': '19.0.1.0.0',
    'summary': "The previous / next arrows of the website's carousels work again outside of the editor",
    'description': """
While a page is edited, Odoo takes from the previous / next arrows of its
carousels what makes them slide the carousel (``data-bs-slide``), as the
editor slides the carousels itself. When the editing ends, it gives them back
what they had when the editing started. A carousel which had already lost it
is then saved without it again, and on the website its arrows do nothing
(only its indicators and the automatic sliding work), while they work in the
editor.

With this module:

- When the editing ends, the arrows of the carousels always get back what
  makes them slide, so that saving a page with such a carousel repairs it.
- When the module is installed, the carousels already saved without it get
  it back.
""",
    'category': 'Website/Website',
    'author': 'EMI Platform',
    'license': 'LGPL-3',
    'depends': ['website'],
    'assets': {
        'website.assets_inside_builder_iframe': [
            'website_carousel_controls_fix/static/src/interactions/**/*',
        ],
        'web.assets_tests': [
            'website_carousel_controls_fix/static/tests/tours/**/*',
        ],
    },
    'post_init_hook': 'post_init_hook',
    'installable': True,
}
