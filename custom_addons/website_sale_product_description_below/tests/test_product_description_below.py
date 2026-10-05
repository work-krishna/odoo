from odoo.tests import HttpCase, tagged

DESCRIPTION = 'Snapdragon 8 Gen 3, 5000 mAh battery and a 200 MP camera'


@tagged('post_install', '-at_install')
class TestProductDescriptionBelow(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.ref('website_sale.product_comment').active = True
        cls.product = cls.env['product.template'].create({
            'name': 'Galaxy S24 Ultra', 'list_price': 100, 'is_published': True,
            'description_ecommerce': f'<p>{DESCRIPTION}</p>',
        })
        cls.bare_product = cls.env['product.template'].create({
            'name': 'Galaxy A15', 'list_price': 100, 'is_published': True,
        })

    def test_description_between_add_to_cart_and_reviews(self):
        html = self.url_open(self.product.website_url).text
        self.assertEqual(html.count(DESCRIPTION), 1, "no longer also under the product name")
        description = html.index(DESCRIPTION)
        self.assertLess(html.index('id="add_to_cart"'), description)
        self.assertLess(html.index('id="o_product_page_description"'), description)
        self.assertLess(description, html.index('id="o_product_page_reviews"'))

    def test_no_section_without_description(self):
        html = self.url_open(self.bare_product.website_url).text
        self.assertIn('id="add_to_cart"', html)
        self.assertNotIn('id="o_product_page_description"', html)

    def test_editor_gets_the_empty_section_for_edit_mode_only(self):
        self.authenticate('admin', 'admin')
        html = self.url_open(self.bare_product.website_url).text
        self.assertRegex(html, r'css_non_editable_mode_hidden[^"]*">\s*<section id="o_product_page_description"')
