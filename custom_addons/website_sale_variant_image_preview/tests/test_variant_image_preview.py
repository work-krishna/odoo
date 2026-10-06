import base64
import io
import json
import re
from datetime import timedelta
from html import unescape

from PIL import Image

from odoo.fields import Command
from odoo.tests import HttpCase, tagged

from odoo.addons.website_sale.tests.common import WebsiteSaleCommon

IMAGE_PREVIEWS = re.compile(r'data-variant-image-previews="([^"]*)"')
DISPLAYED_IMAGE = re.compile(r'<div class="carousel-item[^"]*active">.*?<img src="([^"]*)"', re.S)


def _image(color):
    file = io.BytesIO()
    Image.new('RGB', (800, 800), color).save(file, 'PNG')
    return base64.b64encode(file.getvalue())


class VariantImagePreviewCommon(HttpCase, WebsiteSaleCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.website.product_page_image_layout = 'carousel'
        cls.color, cls.storage = cls.env['product.attribute'].create([{
            'name': 'Color', 'display_type': 'color',
            'value_ids': [Command.create({'name': name, 'html_color': html_color}) for name, html_color in (
                ('Black', '#000000'), ('Blue', '#0000FF'), ('Red', '#FF0000'),
            )],
        }, {
            'name': 'Storage', 'display_type': 'pills',
            'value_ids': [Command.create({'name': name}) for name in ('128 GB', '256 GB')],
        }])
        cls.phone = cls.env['product.template'].create({
            'name': 'Phone',
            'list_price': 100,
            'website_published': True,
            'attribute_line_ids': [
                Command.create({'attribute_id': attribute.id, 'value_ids': [Command.set(attribute.value_ids.ids)]})
                for attribute in (cls.color, cls.storage)
            ],
        })
        cls.images = {color: _image(color) for color in ('black', 'blue', 'navy', 'green', 'gray')}
        # As from the variant's form, Black first while the product has no image
        cls._variant('Black', '128 GB').image_1920 = cls.images['black']
        cls._variant('Blue', '128 GB').image_1920 = cls.images['blue']
        cls._variant('Blue', '256 GB').image_1920 = cls.images['navy']

    @classmethod
    def _variant(cls, *names):
        return cls.phone.product_variant_ids.filtered(
            lambda variant: sorted(variant.product_template_attribute_value_ids.mapped('name')) == sorted(names)
        )

    def _product_page(self, variant=None):
        """ The image previews of the product page of the given variant (by default, of the product), and its
        displayed image
        """
        params = {}
        if variant:
            attribute_values = variant.product_template_attribute_value_ids.product_attribute_value_id
            params['attribute_values'] = ','.join(map(str, attribute_values.ids))
        html = self.url_open(self.phone.website_url, params=params).text
        previews = IMAGE_PREVIEWS.search(html)
        return previews and json.loads(unescape(previews.group(1))), unescape(DISPLAYED_IMAGE.search(html).group(1))


@tagged('post_install', '-at_install')
class TestVariantImagePreview(VariantImagePreviewCommon):

    def test_image_given_to_a_variant_is_its_own(self):
        black_128 = self._variant('Black', '128 GB')
        self.assertEqual(black_128.image_variant_1920, self.images['black'])
        self.assertEqual(self.phone.image_1920, self.images['black'], "The product's image, which it had none")
        self.assertEqual(self._variant('Blue', '128 GB').image_variant_1920, self.images['blue'])
        self.assertEqual(self.phone.image_1920, self.images['black'])

        red_128 = self._variant('Red', '128 GB')
        self.assertFalse(red_128.image_variant_1920)
        self.assertEqual(red_128.image_1920, self.images['black'], "Shows the product's image")

        # Removed: Odoo's
        black_128.image_1920 = False
        self.assertFalse(black_128.image_variant_1920)
        self.assertEqual(self.phone.image_1920, self.images['black'])

        # A product with a single variant: its image is the product's, as in Odoo
        case = self.env['product.template'].create({'name': 'Case'})
        case.product_variant_id.image_1920 = self.images['gray']
        self.assertEqual(case.image_1920, self.images['gray'])
        self.assertFalse(case.product_variant_id.image_variant_1920)

    def test_previews_are_the_images_of_the_variants(self):
        previews, displayed_image = self._product_page()
        black_128, blue_128, blue_256 = (
            self._variant('Black', '128 GB'), self._variant('Blue', '128 GB'), self._variant('Blue', '256 GB')
        )
        self.assertEqual(set(previews), {black_128.combination_indices, blue_128.combination_indices, blue_256.combination_indices})
        # The image shown when the variant is chosen
        self.assertEqual(previews[black_128.combination_indices], displayed_image)
        for variant in (blue_128, blue_256):
            self.assertEqual(previews[variant.combination_indices], self._product_page(variant)[1])
        _previews, displayed_image = self._product_page(self._variant('Red', '256 GB'))
        self.assertNotIn(displayed_image, previews.values())

        # Not without images
        self.phone.product_variant_ids.image_variant_1920 = False
        self.assertIsNone(self._product_page()[0])

    def test_variants_added_or_changed_later(self):
        before = self.cr.now() - timedelta(seconds=1)
        self.phone.product_variant_ids._write({'write_date': before})
        self.phone._write({'write_date': before})
        self.env.invalidate_all()
        blue_128 = self._variant('Blue', '128 GB')
        url = self._product_page()[0][blue_128.combination_indices]

        green = self.env['product.attribute.value'].create({'name': 'Green', 'attribute_id': self.color.id})
        self.phone.attribute_line_ids.filtered(lambda ptal: ptal.attribute_id == self.color).value_ids += green
        green_256 = self._variant('Green', '256 GB')
        green_256.image_1920 = self.images['green']
        blue_128.image_1920 = self.images['navy']
        self._variant('Blue', '256 GB').action_archive()

        previews = self._product_page()[0]
        self.assertEqual(set(previews), {
            self._variant('Black', '128 GB').combination_indices, blue_128.combination_indices, green_256.combination_indices,
        })
        self.assertNotEqual(previews[blue_128.combination_indices], url, "The image changed")
        self.assertEqual(previews[green_256.combination_indices], self._product_page(green_256)[1])

    def test_three_attributes(self):
        material = self.env['product.attribute'].create({
            'name': 'Material', 'display_type': 'radio',
            'value_ids': [Command.create({'name': name}) for name in ('Aluminium', 'Titanium')],
        })
        self.phone.attribute_line_ids = [
            Command.create({'attribute_id': material.id, 'value_ids': [Command.set(material.value_ids.ids)]}),
        ]
        self.assertEqual(len(self.phone.product_variant_ids), 12)
        blue_256_titanium = self._variant('Blue', '256 GB', 'Titanium')
        blue_256_titanium.image_1920 = self.images['green']
        previews, _displayed_image = self._product_page()
        self.assertEqual(previews[blue_256_titanium.combination_indices], self._product_page(blue_256_titanium)[1])

    def test_variant_image_preview_tour(self):
        self.start_tour(self.phone.website_url, 'website_sale_variant_image_preview')


@tagged('post_install', '-at_install')
class TestVariantImagePreviewMobile(VariantImagePreviewCommon):
    browser_size = '375x667'
    touch_enabled = True

    def test_variant_image_preview_tour(self):
        self.start_tour(self.phone.website_url, 'website_sale_variant_image_preview_mobile')
