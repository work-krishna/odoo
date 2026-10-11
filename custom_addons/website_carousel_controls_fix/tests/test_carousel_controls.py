from lxml import etree

from odoo.tests import HttpCase, tagged

from odoo.addons.website_carousel_controls_fix import _repair_carousel_arrows


def _carousel(carousel_id, slide=''):
    """ A carousel as the editor saves it, its arrows without their direction when `slide` is empty """
    return f'''
        <section class="s_carousel_wrapper" data-snippet="s_carousel" data-name="Carousel">
            <div class="s_carousel carousel slide" id="{carousel_id}" data-bs-ride="carousel" data-bs-interval="5000">
                <div class="carousel-inner">
                    <div class="carousel-item active" data-name="Slide"><div class="container"><p>Slide 1</p></div></div>
                    <div class="carousel-item" data-name="Slide"><div class="container"><p>Slide 2</p></div></div>
                </div>
                <button class="carousel-control-prev o_not_editable o_we_no_overlay" aria-label="Previous" title="Previous" data-bs-target="#{carousel_id}" {slide and 'data-bs-slide="prev"'}>
                    <span class="carousel-control-prev-icon" aria-hidden="true"/>
                </button>
                <button class="carousel-control-next o_not_editable o_we_no_overlay" aria-label="Next" title="Next" data-bs-target="#{carousel_id}" {slide and 'data-bs-slide="next"'}>
                    <span class="carousel-control-next-icon" aria-hidden="true"/>
                </button>
                <div class="carousel-indicators o_not_editable">
                    <button type="button" class="active" data-bs-target="#{carousel_id}" data-bs-slide-to="0"/>
                    <button type="button" data-bs-target="#{carousel_id}" data-bs-slide-to="1"/>
                </div>
            </div>
        </section>
    '''


@tagged('post_install', '-at_install')
class TestCarouselControls(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.website = cls.env['website'].get_current_website()
        cls.view = cls.env['ir.ui.view'].create({
            'name': 'Carousel test',
            'type': 'qweb',
            'key': 'website_carousel_controls_fix.carousel_test',
            'website_id': cls.website.id,
            'arch': f'''
                <t name="Carousel test" t-name="website_carousel_controls_fix.carousel_test">
                    <t t-call="website.layout">
                        <div id="wrap" class="oe_structure oe_empty">
                            {_carousel('myCarouselTest')}
                            {_carousel('myCarouselFine', slide=True)}
                        </div>
                    </t>
                </t>
            ''',
        })
        cls.env['website.page'].create({
            'view_id': cls.view.id,
            'url': '/carousel-test',
            'website_id': cls.website.id,
            'is_published': True,
        })

    def _arrows(self, view):
        """ The direction of the arrows of the view's carousels, by carousel and arrow """
        return {
            (arrow.get('data-bs-target'), arrow.get('class').split()[0]): arrow.get('data-bs-slide')
            for arrow in etree.fromstring(view.arch_db).xpath('//button[contains(@class, "carousel-control-")]')
        }

    def test_repair_saved_carousels(self):
        snippet = self.env.ref('website.s_carousel')
        snippet_arch = snippet.arch_db
        _repair_carousel_arrows(self.env)
        self.assertEqual(self._arrows(self.view), {
            ('#myCarouselTest', 'carousel-control-prev'): 'prev',
            ('#myCarouselTest', 'carousel-control-next'): 'next',
            ('#myCarouselFine', 'carousel-control-prev'): 'prev',
            ('#myCarouselFine', 'carousel-control-next'): 'next',
        })
        self.assertEqual(snippet.arch_db, snippet_arch, "Odoo's carousel unchanged")
        html = self.url_open('/carousel-test').text
        self.assertIn('data-bs-target="#myCarouselTest" data-bs-slide="next"', html)

    def test_repair_saved_carousels_twice(self):
        _repair_carousel_arrows(self.env)
        arch = self.view.arch_db
        write_date = self.view.write_date
        _repair_carousel_arrows(self.env)
        self.assertEqual(self.view.arch_db, arch)
        self.assertEqual(self.view.write_date, write_date, "Nothing left to repair")

    def test_saving_a_page_repairs_its_carousels_tour(self):
        self.start_tour(
            self.env['website'].get_client_action_url('/carousel-test'),
            'website_carousel_controls_fix_save',
            login='admin',
        )
        self.assertEqual(self._arrows(self.view)[('#myCarouselTest', 'carousel-control-next')], 'next')
