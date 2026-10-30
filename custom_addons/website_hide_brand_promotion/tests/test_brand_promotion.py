from odoo.tests import HttpCase, tagged


@tagged('post_install', '-at_install')
class TestBrandPromotion(HttpCase):

    def test_no_brand_promotion(self):
        for url in ('/', '/web/login'):
            with self.subTest(url=url):
                html = self.url_open(url).text
                self.assertIn('o_footer_copyright_name', html, "The copyright is still shown")
                self.assertNotIn('o_brand_promotion', html)
                self.assertNotIn('odoo_logo_tiny.png', html)
