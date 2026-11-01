import base64
import io

from PIL import Image

from odoo.tests import HttpCase, tagged


def grid_slide(image_url, active=False):
    """ A slide like the shop's banners: an image filling 9 rows of the grid. """
    return f"""
        <div class="carousel-item pt0 pb0{' active' if active else ''}" data-name="Slide">
            <div class="container oe_unremovable">
                <div class="row o_grid_mode" data-row-count="9">
                    <div class="o_grid_item o_grid_item_image g-height-9 g-col-lg-12 col-lg-12"
                         style="grid-area: 1 / 1 / 10 / 13; z-index: 1; --grid-item-padding-y: 0px; --grid-item-padding-x: 0px;">
                        <img src="{image_url}" class="img img-fluid" alt=""/>
                    </div>
                </div>
            </div>
        </div>"""


def background_slide(image_url, active=False):
    return f"""
        <div class="carousel-item oe_img_bg o_bg_img_center pt48 pb48{' active' if active else ''}"
             style="background-image: url('{image_url}');" data-name="Slide">
            <div class="container oe_unremovable">
                <div class="row"><div class="col-lg-6"><h2>Slide title</h2></div></div>
            </div>
        </div>"""


def carousel(carousel_id, classes, slides, style='', attributes='', ride='false'):
    return f"""
        <section class="s_carousel_wrapper p-0" data-vxml="001" data-vcss="001" data-snippet="s_carousel" data-name="Carousel">
            <div id="{carousel_id}" class="s_carousel s_carousel_default carousel slide {classes}"
                 data-bs-ride="{ride}" data-bs-interval="100000" style="{style}" {attributes}>
                <div class="carousel-inner">{''.join(slides)}</div>
                <button class="carousel-control-prev o_not_editable" data-bs-target="#{carousel_id}" data-bs-slide="prev" aria-label="Previous" title="Previous">
                    <span class="carousel-control-prev-icon" aria-hidden="true"/>
                </button>
                <button class="carousel-control-next o_not_editable" data-bs-target="#{carousel_id}" data-bs-slide="next" aria-label="Next" title="Next">
                    <span class="carousel-control-next-icon" aria-hidden="true"/>
                </button>
            </div>
        </section>"""


class RichCarouselCase(HttpCase):
    """ A page with carousels using the options, without the editor. """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        image = io.BytesIO()
        Image.new('RGB', (1200, 500), (200, 60, 60)).save(image, 'PNG')
        attachment = cls.env['ir.attachment'].create({
            'name': 'rich_carousel_banner.png',
            'datas': base64.b64encode(image.getvalue()),
            'public': True,
        })
        url = f'/web/image/{attachment.id}'
        carousels = ''.join([
            carousel('rc_fixed', 'o_rich_carousel o_rc_height_fixed',
                     [grid_slide(url, active=True), grid_slide(url)],
                     style='--o-rc-height: 300px; --o-rc-height-mobile: 180px;'),
            carousel('rc_ratio', 'o_rich_carousel o_rc_height_ratio o_rc_ratio_12x5 o_rc_mobile_ratio_1x1 o_rc_edge_to_edge',
                     [grid_slide(url, active=True), grid_slide(url)]),
            carousel('rc_background', 'o_rich_carousel o_rc_height_fixed o_rc_fit_stretch',
                     [background_slide(url, active=True), background_slide(url)],
                     style='--o-rc-height: 250px;'),
            carousel('rc_contain', 'o_rich_carousel o_rc_fit_contain o_rc_focus_top carousel-fade',
                     [grid_slide(url, active=True), grid_slide(url)],
                     style='--o-rc-transition: 1.2s; --o-rc-radius: 16px;',
                     attributes='data-bs-pause="false" data-bs-wrap="false" data-bs-touch="false"',
                     # Autoplay: else the carousel doesn't take its options
                     # from the page
                     ride='carousel'),
            # The options do nothing without "Banner options"
            carousel('rc_plain', 'o_rc_height_fixed o_rc_fit_stretch',
                     [grid_slide(url, active=True), grid_slide(url)],
                     style='--o-rc-height: 123px;'),
        ])
        view = cls.env['ir.ui.view'].create({
            'name': 'Rich carousel test',
            'type': 'qweb',
            'key': 'website_rich_carousel.test_page',
            'arch': f"""
                <t t-name="website_rich_carousel.test_page">
                    <t t-call="website.layout">
                        <div id="wrap" class="oe_structure">{carousels}</div>
                    </t>
                </t>""",
        })
        cls.env['website.page'].create({
            'view_id': view.id,
            'url': '/rich-carousel-test',
            'is_published': True,
            'website_id': cls.env['website'].get_current_website().id,
        })


@tagged('post_install', '-at_install')
class TestRichCarousel(RichCarouselCase):

    def test_rich_carousel_desktop(self):
        self.start_tour('/rich-carousel-test', 'website_rich_carousel_desktop')


@tagged('post_install', '-at_install')
class TestRichCarouselMobile(RichCarouselCase):
    browser_size = '375x812'

    def test_rich_carousel_mobile(self):
        self.start_tour('/rich-carousel-test', 'website_rich_carousel_mobile')
