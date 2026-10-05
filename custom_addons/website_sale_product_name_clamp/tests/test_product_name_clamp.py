from odoo.tests import HttpCase, tagged

NAME = 'Redmi 13 Pro+ 5G 12GB RAM 512GB Storage Aurora Purple with 120W Fast Charger and Back Cover'


@tagged('post_install', '-at_install')
class TestProductNameClamp(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.product = cls.env['product.template'].create({
            'name': NAME, 'list_price': 100, 'is_published': True,
        })

    def test_shop_card_carries_the_full_name_on_hover(self):
        html = self.url_open('/shop?search=Aurora').text
        self.assertIn('id="o_wsale_products_grid"', html, "the clamp is scoped to this grid")
        self.assertIn(f'title="{NAME}"', html)

    def test_product_page_is_unchanged(self):
        html = self.url_open(self.product.website_url).text
        self.assertNotIn('id="o_wsale_products_grid"', html, "so the clamp does not apply here")
        self.assertIn(NAME, html)
