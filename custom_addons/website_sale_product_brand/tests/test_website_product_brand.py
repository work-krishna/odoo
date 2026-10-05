import json
import re
from html import unescape

from odoo.tests import HttpCase, tagged

BRAND = re.compile(r'<div class="o_wsale_product_brand[^"]*">([^<]*)</div>')
JSON_LD = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.S)


@tagged('post_install', '-at_install')
class TestWebsiteProductBrand(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.apple = cls.env['product.brand'].create({'name': 'Apple'})
        cls.iphone = cls.env['product.template'].create({
            'name': 'iPhone 17 Pro', 'list_price': 189999, 'is_published': True,
            'product_brand_id': cls.apple.id,
        })

    def _shown_brands(self, product):
        return BRAND.findall(self.url_open(product.website_url).text)

    def _markup(self, product):
        """ The product's structured data: the list next to the company's """
        scripts = [json.loads(unescape(s)) for s in JSON_LD.findall(self.url_open(product.website_url).text)]
        return next(data for data in scripts if isinstance(data, list))[0]

    def test_brand_under_the_rating(self):
        self.env.ref('website_sale.product_comment').active = True
        html = self.url_open(self.iphone.website_url).text
        self.assertEqual(BRAND.findall(html), ['Apple'])
        brand = html.index('o_wsale_product_brand')
        self.assertLess(html.index('<h1'), brand)
        self.assertLess(html.index('o_product_page_reviews_link'), brand)
        self.assertLess(brand, html.index('id="add_to_cart"'))
        self.assertEqual(self._markup(self.iphone)['brand'], {'@type': 'Brand', 'name': 'Apple'})

    def test_brand_under_the_name_without_ratings(self):
        self.env.ref('website_sale.product_comment').active = False
        html = self.url_open(self.iphone.website_url).text
        self.assertNotIn('o_product_page_reviews_link', html)
        self.assertEqual(BRAND.findall(html), ['Apple'])
        self.assertLess(html.index('<h1'), html.index('o_wsale_product_brand'))

    def test_hidden_brand_stays_assigned(self):
        oem = self.env['product.template'].create({
            'name': 'Internal OEM Product', 'list_price': 100, 'is_published': True,
            'product_brand_id': self.env['product.brand'].create({'name': 'Xiaomi'}).id,
            'website_show_brand': False,
        })
        self.assertEqual(self._shown_brands(oem), [])
        self.assertNotIn('brand', self._markup(oem))
        self.assertEqual(oem.product_brand_id.name, 'Xiaomi')

    def test_no_brand_is_never_shown(self):
        momo = self.env['product.template'].create({'name': 'Chicken Momo', 'list_price': 250, 'is_published': True})
        self.assertTrue(momo.website_show_brand)
        self.assertEqual(momo.product_brand_id, self.env.ref('product_brand.product_brand_no_brand'))
        self.assertEqual(self._shown_brands(momo), [])
        self.assertNotIn('brand', self._markup(momo))
