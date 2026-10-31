from odoo.fields import Command
from odoo.tests import HttpCase, tagged

from odoo.addons.website_sale.tests.common import WebsiteSaleCommon


@tagged('post_install', '-at_install')
class TestCategoriesArrows(HttpCase, WebsiteSaleCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.ref('website_sale.products_categories_top').active = True
        # More categories than fit at the top of the shop
        categories = cls.env['product.public.category'].create([
            {'name': f'Arrows Category {index:02}'} for index in range(1, 16)
        ])
        cls.env['product.template'].create([{
            'name': f'Arrows Product {category.name}',
            'list_price': 100,
            'website_published': True,
            'public_categ_ids': [Command.link(category.id)],
        } for category in categories])

    def test_arrows_rendered(self):
        html = self.url_open('/shop').text
        self.assertIn('o_wsale_filmstrip_arrow_prev', html)
        self.assertIn('o_wsale_filmstrip_arrow_next', html)

    def test_categories_arrows_tour(self):
        self.start_tour('/shop', 'website_sale_categories_arrows')
