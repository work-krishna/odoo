import json
import re
from html import unescape

from odoo.fields import Command
from odoo.tests import HttpCase, tagged

BRAND = re.compile(r'<div class="o_wsale_product_brand[^"]*">\s*<span[^>]*>Product by:</span>\s*<a href="([^"]*)">([^<]*)</a>')
BRAND_FILTER = re.compile(r'<input type="checkbox" name="brand" class="form-check-input" id="o_products_attributes_brands_\d+" value="([^"]*)"( checked="[^"]*")?')
JSON_LD = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.S)


@tagged('post_install', '-at_install')
class TestWebsiteProductBrand(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.ref('website_sale.products_attributes').active = True
        Brand = cls.env['product.brand']
        cls.apple, cls.samsung, cls.xiaomi = Brand.create([{'name': 'Apple'}, {'name': 'Samsung'}, {'name': 'Xiaomi'}])
        cls.no_brand = cls.env.ref('product_brand.product_brand_no_brand')
        storage = cls.env['product.attribute'].create({
            'name': 'Storage', 'display_type': 'radio',
            'value_ids': [Command.create({'name': name}) for name in ('128 GB', '256 GB', '512 GB')],
        })
        gb128, gb256, gb512 = storage.value_ids
        # Its own category, so the shop's page only has these products
        cls.category = cls.env['product.public.category'].create({'name': 'Brand Test'})
        cls.iphone, cls.galaxy, cls.oem, cls.momo = cls.env['product.template'].create([{
            'name': 'iPhone 17 Pro', 'product_brand_id': cls.apple.id,
            'attribute_line_ids': [Command.create({'attribute_id': storage.id, 'value_ids': [Command.set((gb128 | gb256).ids)]})],
        }, {
            'name': 'Galaxy S25', 'product_brand_id': cls.samsung.id,
            'attribute_line_ids': [Command.create({'attribute_id': storage.id, 'value_ids': [Command.set((gb256 | gb512).ids)]})],
        }, {
            'name': 'Internal OEM Product', 'product_brand_id': cls.xiaomi.id, 'website_show_brand': False,
        }, {
            'name': 'Chicken Momo',
        }])
        (cls.iphone | cls.galaxy | cls.oem | cls.momo).write({
            'list_price': 100, 'is_published': True, 'public_categ_ids': [Command.set(cls.category.ids)],
        })
        cls.shop_url = f"/shop/category/{cls.env['ir.http']._slug(cls.category)}"

    def _slug(self, brand):
        return self.env['ir.http']._slug(brand)

    def _shown_brands(self, product):
        return [name for _url, name in BRAND.findall(self.url_open(product.website_url).text)]

    def _markup(self, product):
        """ The product's structured data: the list next to the company's """
        scripts = [json.loads(unescape(s)) for s in JSON_LD.findall(self.url_open(product.website_url).text)]
        return next(data for data in scripts if isinstance(data, list))[0]

    def _shop(self, brands='', **params):
        return self.url_open(self.shop_url, params={'brand': brands, **params} if brands else params).text

    def _brand_filter(self, html):
        """ The brands to filter on, and the ones checked """
        values = BRAND_FILTER.findall(html)
        return [value for value, _checked in values], [value for value, checked in values if checked]

    def test_brand_under_the_rating(self):
        self.env.ref('website_sale.product_comment').active = True
        html = self.url_open(self.iphone.website_url).text
        self.assertEqual(BRAND.findall(html), [(f'/shop?brand={self._slug(self.apple)}', 'Apple')])
        brand = html.index('o_wsale_product_brand')
        self.assertLess(html.index('<h1'), brand)
        self.assertLess(html.index('o_product_page_reviews_link'), brand)
        self.assertLess(brand, html.index('id="add_to_cart"'))
        self.assertEqual(self._markup(self.iphone)['brand'], {'@type': 'Brand', 'name': 'Apple'})

    def test_brand_under_the_name_without_ratings(self):
        self.env.ref('website_sale.product_comment').active = False
        html = self.url_open(self.iphone.website_url).text
        self.assertNotIn('o_product_page_reviews_link', html)
        self.assertEqual(len(BRAND.findall(html)), 1)
        self.assertLess(html.index('<h1'), html.index('o_wsale_product_brand'))

    def test_shop_filtered_on_brands(self):
        html = self._shop()
        self.assertEqual(self._brand_filter(html), ([self._slug(self.apple), self._slug(self.samsung)], []))
        self.assertLess(html.index('o_wsale_brand_filter'), html.index('>Storage<'), "the brands come first")

        html = self._shop(self._slug(self.apple))
        self.assertIn('iPhone 17 Pro', html)
        self.assertNotIn('Galaxy S25', html)
        self.assertNotIn('Chicken Momo', html)
        self.assertEqual(self._brand_filter(html)[1], [self._slug(self.apple)])
        # Kept when changing filters, cleared with them
        self.assertIn(f'action="{self.shop_url}?brand={self._slug(self.apple)}"', html)
        self.assertIn(f'href="{self.shop_url}"', re.search(r'<a [^>]*title="Clear Filters"[^>]*>', html).group())

        html = self._shop(f'{self._slug(self.apple)},{self.samsung.id}')
        self.assertIn('iPhone 17 Pro', html)
        self.assertIn('Galaxy S25', html)
        self.assertNotIn('Chicken Momo', html)
        self.assertEqual(self._brand_filter(html)[1], [self._slug(self.apple), self._slug(self.samsung)])

    def test_brand_filter_with_attributes(self):
        storage_512 = self.galaxy.attribute_line_ids.value_ids.filtered(lambda v: v.name == '512 GB')
        attribute_values = f'{storage_512.attribute_id.id}-{storage_512.id}'
        html = self._shop(self._slug(self.apple), attribute_values=attribute_values)
        self.assertNotIn('iPhone 17 Pro', html)
        self.assertNotIn('Galaxy S25', html)
        html = self._shop(self._slug(self.samsung), attribute_values=attribute_values)
        self.assertIn('Galaxy S25', html)

    def test_no_brand_filter_for_a_single_brand(self):
        self.assertFalse(self._brand_filter(self._shop(search='iPhone'))[0])
        self.assertEqual(self._brand_filter(self._shop(self._slug(self.apple), search='iPhone')),
                         ([self._slug(self.apple)], [self._slug(self.apple)]), "still shown to uncheck it")

    def test_hidden_brand_stays_assigned(self):
        self.assertEqual(self._shown_brands(self.oem), [])
        self.assertNotIn('brand', self._markup(self.oem))
        self.assertEqual(self.oem.product_brand_id, self.xiaomi)
        self.assertNotIn(self._slug(self.xiaomi), self._brand_filter(self._shop())[0])
        self.assertNotIn('Internal OEM Product', self._shop(self._slug(self.xiaomi)))

    def test_no_brand_is_never_shown(self):
        self.assertTrue(self.momo.website_show_brand)
        self.assertEqual(self.momo.product_brand_id, self.no_brand)
        self.assertEqual(self._shown_brands(self.momo), [])
        self.assertNotIn('brand', self._markup(self.momo))
        html = self._shop(self._slug(self.no_brand))
        self.assertIn('Chicken Momo', html, "not a filter")
        self.assertIn('Galaxy S25', html)
        self.assertEqual(self._brand_filter(html), ([self._slug(self.apple), self._slug(self.samsung)], []))

    def test_brand_filter_tour(self):
        self.start_tour(self.shop_url, 'website_sale_product_brand_filter')
