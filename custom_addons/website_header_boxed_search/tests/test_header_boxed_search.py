from lxml import html

from odoo.tests import HttpCase, tagged


@tagged('post_install', '-at_install')
class TestHeaderBoxedSearch(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.website = cls.env.ref('website.default_website')
        cls._set_views(**{'website.template_header_default': False, 'website.template_header_boxed': True})

    @classmethod
    def _set_views(cls, **active_by_key):
        """ Like the website editor's options: only for the website, and
        disabling first, as two headers can't be active at once """
        views = cls.env['ir.ui.view'].with_context(website_id=cls.website.id, active_test=False)
        views = views.search([('key', 'in', list(active_by_key))]).filter_duplicate()
        for view in views.sorted(lambda view: active_by_key[view.key]):
            view.active = active_by_key[view.key]

    def _main_nav(self):
        page = html.fromstring(self.url_open('/').content)
        return page.xpath("//header[@id='top']//div[@id='o_main_nav']")[0]

    def test_search_field(self):
        nav = self._main_nav()
        field = nav.xpath("./ul[contains(@class, 'top_menu')]/following-sibling::*[1][contains(@class, 'o_header_boxed_search')]")
        self.assertTrue(field, "Right after the menu")
        items = field[0].xpath('./li')
        self.assertEqual(len(items), 1, "Only the search: the icons placed next to it (cart, ...) stay on the right")
        self.assertTrue(items[0].xpath(".//form[contains(@class, 'o_searchbar_form')]//input[@name='search']"))
        self.assertFalse(nav.xpath(".//*[@data-bs-target='#o_search_modal']"), "No more search icon")
        self.assertFalse(nav.xpath(".//*[@id='o_search_modal']"), "Nor search window")

    def test_search_bar_option(self):
        self._set_views(**{'website.header_search_box': False})
        nav = self._main_nav()
        self.assertFalse(nav.xpath(".//*[contains(@class, 'o_header_boxed_search')]"))
        self.assertFalse(nav.xpath(".//input[@name='search']"))

    def test_other_headers(self):
        self._set_views(**{'website.template_header_boxed': False, 'website.template_header_default': True})
        nav = self._main_nav()
        self.assertFalse(nav.xpath(".//*[contains(@class, 'o_header_boxed_search')]"))
        self.assertTrue(nav.xpath(".//*[@data-bs-target='#o_search_modal']"), "Still the search icon of the default header")

    def test_tour(self):
        # A menu short enough for the bar
        self.website.menu_id.child_id[3:].unlink()
        self.start_tour('/', 'website_header_boxed_search')

    def test_tour_long_menu(self):
        self.env['website.menu'].create([{
            'name': f'Long menu item {number}',
            'url': '/',
            'parent_id': self.website.menu_id.id,
            'website_id': self.website.id,
        } for number in range(1, 16)])
        self.start_tour('/', 'website_header_boxed_search_long_menu')
