from lxml import html as lxml_html

from odoo.tests import HttpCase, tagged

from odoo.addons.website_sale.tests.common import WebsiteSaleCommon


@tagged('post_install', '-at_install')
class TestBuyNowFirst(HttpCase, WebsiteSaleCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.phone = cls.env['product.template'].create({
            'name': 'Phone',
            'list_price': 100,
            'website_published': True,
        })
        cls.env.ref('website_sale.product_buy_now').active = True

    def _buttons(self):
        """ The buttons next to the quantity, in their order, and their classes """
        page = lxml_html.fromstring(self.url_open(self.phone.website_url).text)
        return [
            ('buy_now' if 'o_we_buy_now' in button.classes else button.get('id'), set(button.classes))
            for button in page.get_element_by_id('add_to_cart_wrap').xpath('./a')
        ]

    def test_buy_now_first(self):
        (buy_now, buy_now_classes), (add_to_cart, add_to_cart_classes) = self._buttons()
        self.assertEqual((buy_now, add_to_cart), ('buy_now', 'add_to_cart'))
        self.assertLessEqual({'btn-primary', 'flex-grow-1'}, buy_now_classes)
        self.assertFalse({'btn-outline-primary', 'w-100'} & buy_now_classes)
        self.assertLessEqual({'btn-outline-primary', 'w-100', 'js_check_product', 'a-submit'}, add_to_cart_classes)
        self.assertFalse({'btn-primary', 'flex-grow-1'} & add_to_cart_classes)

    def test_buy_now_first_large(self):
        """ As on the shop: large buttons and quantity """
        for view in ('cta_wrapper_large', 'product_buy_now_large', 'product_quantity_large'):
            self.env.ref(f'website_sale.{view}').active = True
        (buy_now, buy_now_classes), (add_to_cart, add_to_cart_classes) = self._buttons()
        self.assertEqual((buy_now, add_to_cart), ('buy_now', 'add_to_cart'))
        self.assertLessEqual({'btn-primary', 'btn-lg'}, buy_now_classes)
        self.assertLessEqual({'btn-outline-primary', 'btn-lg'}, add_to_cart_classes)

    def test_without_buy_now(self):
        self.env.ref('website_sale.product_buy_now').active = False
        [(add_to_cart, add_to_cart_classes)] = self._buttons()
        self.assertEqual(add_to_cart, 'add_to_cart')
        self.assertLessEqual({'btn-primary', 'flex-grow-1'}, add_to_cart_classes)
        self.assertNotIn('btn-outline-primary', add_to_cart_classes)

    def test_buy_now_first_tour(self):
        self.start_tour(self.phone.website_url, 'website_sale_buy_now_first')
