import base64
import io

from lxml import html as lxml_html
from PIL import Image

from odoo.fields import Command
from odoo.tests import HttpCase, tagged

from odoo.addons.website_sale.tests.common import WebsiteSaleCommon

VIDEO_URL = 'https://www.youtube.com/watch?v=dQw4w9WgXcQ'


def _image(color):
    file = io.BytesIO()
    Image.new('RGB', (800, 800), color).save(file, 'PNG')
    return base64.b64encode(file.getvalue())


def _carousel(html):
    """ The slides and the thumbnails of the product carousel of the given HTML, and which ones are active

    :return: the slides, the indexes of the active slides, the indexes of the active thumbnails
    """
    carousel = lxml_html.fromstring(html).get_element_by_id('o-carousel-product')
    slides = carousel.xpath('.//div[contains(concat(" ", normalize-space(@class), " "), " carousel-item ")]')
    thumbnails = carousel.xpath('.//ol[contains(@class, "carousel-indicators")]/li')
    return (
        slides,
        [index for index, slide in enumerate(slides) if 'active' in slide.classes],
        [index for index, thumbnail in enumerate(thumbnails) if 'active' in thumbnail.classes],
    )


def _image_name(slide):
    return slide.xpath('.//img[contains(@class, "product_detail_img")]/@alt')[0]


@tagged('post_install', '-at_install')
class TestProductFirstMedia(HttpCase, WebsiteSaleCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.website.product_page_image_layout = 'carousel'
        color = cls.env['product.attribute'].create({
            'name': 'Color',
            'display_type': 'color',
            'value_ids': [
                Command.create({'name': 'Black', 'html_color': '#000000'}),
                Command.create({'name': 'Blue', 'html_color': '#0000FF'}),
            ],
        })
        cls.phone, cls.watch, cls.case = cls.env['product.template'].create([{
            'name': 'Phone',
            'image_1920': _image('red'),
            'attribute_line_ids': [
                Command.create({'attribute_id': color.id, 'value_ids': [Command.set(color.value_ids.ids)]}),
            ],
            'product_template_image_ids': [
                Command.create({'name': 'Front', 'image_1920': _image('green'), 'sequence': 1}),
                Command.create({'name': 'Side', 'image_1920': _image('yellow'), 'sequence': 2}),
            ],
        }, {
            'name': 'Watch',
            'image_1920': _image('red'),
            'product_template_image_ids': [
                Command.create({'name': 'Watch video', 'video_url': VIDEO_URL, 'sequence': 1}),
                Command.create({'name': 'Strap', 'image_1920': _image('green'), 'sequence': 2}),
            ],
        }, {
            'name': 'Case',
            'image_1920': _image('red'),
        }])
        (cls.phone | cls.watch | cls.case).write({'website_published': True, 'list_price': 100})
        cls.black, cls.blue = cls.phone.product_variant_ids.sorted(
            lambda variant: variant.product_template_attribute_value_ids.name
        )
        cls.blue.write({
            'image_variant_1920': _image('blue'),
            'product_variant_image_ids': [
                Command.create({'name': 'Blue back', 'image_1920': _image('navy')}),
            ],
        })

    def _product_page(self, template, variant=None):
        params = {}
        if variant:
            attribute_values = variant.product_template_attribute_value_ids.product_attribute_value_id
            params['attribute_values'] = ','.join(map(str, attribute_values.ids))
        return self.url_open(template.website_url, params=params).text

    def test_opens_on_first_product_media(self):
        slides, active_slides, active_thumbnails = _carousel(self._product_page(self.phone, self.black))
        self.assertEqual([_image_name(slide) for slide in slides], ['Phone', 'Front', 'Side'])
        self.assertEqual(active_slides, [1], "The first Extra Product Media, not the image of the variant")
        self.assertEqual(active_thumbnails, [1])

    def test_opens_on_first_variant_media(self):
        slides, active_slides, active_thumbnails = _carousel(self._product_page(self.phone, self.blue))
        self.assertEqual([_image_name(slide) for slide in slides], ['Phone', 'Blue back', 'Front', 'Side'])
        self.assertEqual(active_slides, [1], "The first Extra Variant Media comes before the product's")
        self.assertEqual(active_thumbnails, [1])

    def test_opens_on_first_media_video(self):
        slides, active_slides, active_thumbnails = _carousel(self._product_page(self.watch))
        self.assertEqual(active_slides, [1])
        self.assertEqual(active_thumbnails, [1])
        self.assertTrue(slides[1].xpath('.//iframe'), "The video is shown")

    def test_product_without_media(self):
        slides, active_slides, active_thumbnails = _carousel(self._product_page(self.case))
        self.assertEqual(len(slides), 1)
        self.assertEqual(active_slides, [0], "Its image, as in Odoo")
        self.assertEqual(active_thumbnails, [], "No thumbnails for a single image")

    def test_grid_layout(self):
        self.website.product_page_image_layout = 'grid'
        page = lxml_html.fromstring(self._product_page(self.phone, self.black))
        self.assertIsNone(page.find('.//*[@id="o-carousel-product"]'))
        self.assertEqual(len(page.get_element_by_id('o-grid-product').xpath('.//img[contains(@class, "product_detail_img")]')), 3)

    def test_chosen_variant_shows_its_image(self):
        """ When the visitor picks a variant, its images are rendered again, from its own image """
        combination_info = self.make_jsonrpc_request('/website_sale/get_combination_info', {
            'product_template_id': self.phone.id,
            'product_id': self.black.id,
            'combination': self.blue.product_template_attribute_value_ids.ids,
            'add_qty': 1,
        })
        slides, active_slides, active_thumbnails = _carousel(combination_info['carousel'])
        self.assertEqual([_image_name(slide) for slide in slides], ['Phone', 'Blue back', 'Front', 'Side'])
        self.assertEqual(active_slides, [0])
        self.assertEqual(active_thumbnails, [0])
        self.assertIn(f'/product.product/{self.blue.id}/image_1024/', slides[0].xpath('.//img/@src')[0])

    def test_product_first_media_navigation_tour(self):
        self.start_tour(self.phone.website_url, 'website_sale_product_first_media_navigation')

    def test_product_first_media_variant_tour(self):
        self.start_tour(self.phone.website_url, 'website_sale_product_first_media_variant')
