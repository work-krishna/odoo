import json
import re
from html import unescape

from odoo.fields import Command
from odoo.tests import HttpCase, JsonRpcException, tagged

from odoo.addons.website_sale.tests.common import WebsiteSaleCommon

ATTRIBUTE_EXCLUSIONS = re.compile(r'data-attribute-exclusions="([^"]*)"')
PRODUCT_ID = re.compile(r'class="o_not_editable product_id" name="product_id" value="(\d+)"')


@tagged('post_install', '-at_install')
class TestVariantPublish(HttpCase, WebsiteSaleCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.color, cls.storage = cls.env['product.attribute'].create([{
            'name': 'Color', 'display_type': 'color',
            'value_ids': [Command.create({'name': name, 'html_color': html_color}) for name, html_color in (
                ('Black', '#000000'), ('Blue', '#0000FF'), ('Red', '#FF0000'),
            )],
        }, {
            'name': 'Storage', 'display_type': 'pills',
            'value_ids': [Command.create({'name': name}) for name in ('128 GB', '256 GB')],
        }])
        # Their own category, so the shop's page only has them
        cls.category = cls.env['product.public.category'].create({'name': 'Variant Publish'})
        cls.phone, cls.case = cls.env['product.template'].create([{
            'name': 'Publish Phone',
            'attribute_line_ids': [
                Command.create({'attribute_id': attribute.id, 'value_ids': [Command.set(attribute.value_ids.ids)]})
                for attribute in (cls.color, cls.storage)
            ],
        }, {
            'name': 'Publish Case',
            'attribute_line_ids': [
                Command.create({'attribute_id': cls.color.id, 'value_ids': [Command.set(cls.color.value_ids.ids)]}),
            ],
        }])
        (cls.phone | cls.case).write({
            'list_price': 100, 'taxes_id': [Command.clear()], 'website_published': True,
            'public_categ_ids': [Command.set(cls.category.ids)],
        })

    @classmethod
    def _variant(cls, template, *names):
        return template.product_variant_ids.filtered(
            lambda variant: sorted(variant.product_template_attribute_value_ids.mapped('name')) == sorted(names)
        )

    def _product_page(self, template, variant=None):
        params = {}
        if variant:
            attribute_values = variant.product_template_attribute_value_ids.product_attribute_value_id
            params['attribute_values'] = ','.join(map(str, attribute_values.ids))
        html = self.url_open(template.website_url, params=params).text
        exclusions = json.loads(unescape(ATTRIBUTE_EXCLUSIONS.search(html).group(1)))
        product_id = int(PRODUCT_ID.search(html).group(1))
        values = set(re.findall(r'input[^>]* data-value-name="([^"]*)"', html))
        return product_id, exclusions, values

    def _combinations(self, *variants):
        return {frozenset(variant.product_template_attribute_value_ids.ids) for variant in variants}

    def test_variants_are_published_by_default(self):
        self.assertTrue(all(self.phone.product_variant_ids.mapped('is_variant_published')))
        green = self.env['product.attribute.value'].create({'name': 'Green', 'attribute_id': self.color.id})
        self.phone.attribute_line_ids.filtered(lambda ptal: ptal.attribute_id == self.color).value_ids += green
        self.assertTrue(self._variant(self.phone, 'Green', '256 GB').is_variant_published)

    def test_product_page(self):
        product_id, exclusions, values = self._product_page(self.phone)
        self.assertEqual(product_id, self._variant(self.phone, 'Black', '128 GB').id)
        self.assertEqual(exclusions['archived_combinations'], [])
        self.assertEqual(values, {'Black', 'Blue', 'Red', '128 GB', '256 GB'})

        blue_256 = self._variant(self.phone, 'Blue', '256 GB')
        (self._variant(self.phone, 'Red', '128 GB') | self._variant(self.phone, 'Red', '256 GB') | blue_256).is_variant_published = False
        product_id, exclusions, values = self._product_page(self.phone)
        self.assertEqual(values, {'Black', 'Blue', '128 GB', '256 GB'}, "No more Red variants")
        self.assertEqual(
            {frozenset(combination) for combination in exclusions['archived_combinations']},
            self._combinations(self._variant(self.phone, 'Red', '128 GB'), self._variant(self.phone, 'Red', '256 GB'), blue_256),
            "Grayed out",
        )

        # Opens on a published variant
        self._variant(self.phone, 'Black', '128 GB').is_variant_published = False
        self.assertEqual(self._product_page(self.phone)[0], self._variant(self.phone, 'Black', '256 GB').id)
        self.assertEqual(self._product_page(self.phone, blue_256)[0], self._variant(self.phone, 'Black', '256 GB').id)

        # A single attribute
        self._variant(self.case, 'Red').is_variant_published = False
        _product_id, _exclusions, values = self._product_page(self.case)
        self.assertEqual(values, {'Black', 'Blue'})

    def test_unpublished_variant_cannot_be_bought(self):
        red_128, blue_128 = self._variant(self.phone, 'Red', '128 GB'), self._variant(self.phone, 'Blue', '128 GB')
        red_128.is_variant_published = False

        info = self.make_jsonrpc_request('/website_sale/get_combination_info', {
            'product_template_id': self.phone.id, 'product_id': blue_128.id,
            'combination': red_128.product_template_attribute_value_ids.ids, 'add_qty': 1,
        })
        self.assertEqual(info['product_id'], red_128.id)
        self.assertFalse(info['is_combination_possible'])

        with self.assertRaises(JsonRpcException):
            self.make_jsonrpc_request('/shop/cart/add', {'product_template_id': self.phone.id, 'product_id': red_128.id})
        self.make_jsonrpc_request('/shop/cart/add', {'product_template_id': self.phone.id, 'product_id': blue_128.id})
        cart = self.env['sale.order'].search([('website_id', '=', self.website.id)], order='id desc', limit=1)
        self.assertEqual(cart.order_line.product_id, blue_128)

    def test_window_to_choose_the_options(self):
        red_variants = self._variant(self.phone, 'Red', '128 GB') | self._variant(self.phone, 'Red', '256 GB')
        (red_variants | self._variant(self.phone, 'Black', '128 GB')).is_variant_published = False
        values = self.make_jsonrpc_request('/website_sale/product_configurator/get_values', {
            'product_template_id': self.phone.id, 'quantity': 1, 'currency_id': self.phone.currency_id.id,
            'so_date': '2026-01-01 00:00:00',
        })['products'][0]
        self.assertEqual(
            {frozenset(combination) for combination in values['archived_combinations']},
            self._combinations(*red_variants, self._variant(self.phone, 'Black', '128 GB')),
        )
        selected = {ptav_id for line in values['attribute_lines'] for ptav_id in line['selected_attribute_value_ids']}
        self.assertEqual(selected, set(self._variant(self.phone, 'Black', '256 GB').product_template_attribute_value_ids.ids))

    def test_shop(self):
        shop_url = f"/shop/category/{self.env['ir.http']._slug(self.category)}"
        self.assertIn('Publish Case', self.url_open(shop_url).text)
        self._variant(self.case, 'Black').is_variant_published = False
        self.assertIn('Publish Case', self.url_open(shop_url).text)
        self.case.product_variant_ids.is_variant_published = False
        html = self.url_open(shop_url).text
        self.assertNotIn('Publish Case', html, "All its variants are hidden")
        self.assertIn('Publish Phone', html)

    def test_backend_is_not_affected(self):
        red_128 = self._variant(self.phone, 'Red', '128 GB')
        red_128.is_variant_published = False
        self.assertTrue(self.phone._is_combination_possible(red_128.product_template_attribute_value_ids))
        self.assertEqual(self.phone._get_attribute_exclusions()['archived_combinations'], [])
        order = self.env['sale.order'].create({
            'partner_id': self.partner.id, 'order_line': [Command.create({'product_id': red_128.id})],
        })
        self.assertEqual(order.order_line.price_unit, 100)

    def test_variant_publish_tour(self):
        (self._variant(self.phone, 'Red', '128 GB') | self._variant(self.phone, 'Red', '256 GB')).is_variant_published = False
        self._variant(self.phone, 'Blue', '256 GB').is_variant_published = False
        self.start_tour(self.phone.website_url, 'website_sale_variant_publish')

    def test_variant_list_toggle_tour(self):
        self.start_tour('/odoo/action-product.product_normal_action_sell?view_type=list', 'website_sale_variant_publish_list', login='admin')
        self.assertFalse(self._variant(self.phone, 'Red', '128 GB').is_variant_published)
        self.assertEqual(self.phone.product_variant_ids.filtered(lambda variant: not variant.is_variant_published), self._variant(self.phone, 'Red', '128 GB'))
        self.assertTrue(self.phone.is_published)
