{
    'name': 'Website: Rich Carousel',
    'version': '19.0.1.0.0',
    'summary': "Banner options for the website's carousels: height, image fit, edge to edge, arrows and sliding",
    'description': """
In the editor, a carousel's height comes from its slides' content (the tallest
one wins), its images can only be cropped to fill it, and its slides leave
room on their sides for the arrows. Making a banner of it is hard.

With this module, a carousel has "Banner options" in the editor. Once turned
on:

- Banner height: Auto (as without the module), Fixed (a height in pixels for
  desktop, tablet and mobile screens) or Ratio (e.g. 12:5, or "Match image":
  the ratio of the image of the slide, so that it's shown whole), with a
  ratio of its own for mobile screens. The images of the slides fill the
  height, and their text can be put at the top, middle or bottom.
- Image fit: Cover (fills the banner, cropping the images), Contain (shows the
  whole images) or Stretch (fills the banner, distorting the images), and the
  part of the images kept in view (Image focus).
- Edge to edge: the slides use the whole width of the carousel, under its
  arrows.
- Rounded corners.
- Arrow size, and arrows shown only when the mouse is over the banner.
- Transition time, pause on hover, loop and swipe.

Turned off, they're all removed.
""",
    'category': 'Website/Website',
    'author': 'EMI Platform',
    'license': 'LGPL-3',
    'depends': ['website'],
    'assets': {
        'web.assets_frontend': [
            'website_rich_carousel/static/src/scss/**/*',
        ],
        'website.website_builder_assets': [
            'website_rich_carousel/static/src/builder/**/*',
        ],
        'web.assets_tests': [
            'website_rich_carousel/static/tests/tours/**/*',
        ],
        'web.assets_unit_tests': [
            'website_rich_carousel/static/tests/*.test.js',
        ],
    },
    'installable': True,
}
