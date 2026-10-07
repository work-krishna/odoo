from lxml import html

from odoo.fields import Command
from odoo.tests import HttpCase, tagged

from odoo.addons.website_sale.tests.common import WebsiteSaleCommon
from odoo.addons.website_sale_shop_show_more import post_init_hook


@tagged('post_install', '-at_install')
class TestShopShowMore(HttpCase, WebsiteSaleCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Their own category, so the shop's page only has them
        cls.category = cls.env['product.public.category'].create({'name': 'Show More'})
        cls.category_path = f"/shop/category/{cls.env['ir.http']._slug(cls.category)}"
        cls.products = cls.env['product.template'].create([{
            'name': f'Show More {number:02}',
            'list_price': 10,
            'taxes_id': [Command.clear()],
            'website_published': True,
            'public_categ_ids': [Command.set(cls.category.ids)],
        } for number in range(1, 52)])

    def _shop_page(self, url):
        page = html.fromstring(self.url_open(url).content)
        products = page.xpath("//section[@id='o_wsale_products_grid']/div[@data-product-template-id]")
        button = page.xpath("//div[@id='o_wsale_pager']/a[contains(@class, 'o_wsale_show_more')]")
        self.assertFalse(page.xpath("//*[contains(@class, 'pagination')]"), "No page numbers")
        return [int(product.get('data-product-template-id')) for product in products], button[0].get('href') if button else None

    def test_products_per_page_follow_columns(self):
        for columns, products in ((5, 50), (4, 48), (3, 48), (2, 40)):
            self.website.shop_ppr = columns
            self.assertEqual(self.website.shop_ppg, products, f"{columns} columns")

        self.website.shop_ppg = 30
        self.website.shop_gap = '8px'
        self.assertEqual(self.website.shop_ppg, 30, "Can be changed by hand")
        self.website.shop_ppr = 4
        self.assertEqual(self.website.shop_ppg, 48, "Until the columns change")

    def test_website_editor(self):
        self.authenticate('admin', 'admin')
        website = self.env['website'].get_current_website()
        self.make_jsonrpc_request('/shop/config/website', {'shop_ppr': 5})
        self.assertEqual(website.shop_ppg, 50)
        self.make_jsonrpc_request('/shop/config/website', {'shop_ppr': 2})
        self.assertEqual(website.shop_ppg, 40)

    def test_new_and_existing_websites(self):
        self.assertEqual(self.env['website'].create({'name': 'Default columns'}).shop_ppg, 48, "3 columns")
        self.assertEqual(self.env['website'].create({'name': '5 columns', 'shop_ppr': 5}).shop_ppg, 50)

        self.website.write({'shop_ppr': 2})
        self.website.shop_ppg = 21
        post_init_hook(self.env)
        self.assertEqual(self.website.shop_ppg, 40)

    def test_shop_page(self):
        self.env['website'].get_current_website().shop_ppr = 5
        products, button = self._shop_page(self.category_path)
        self.assertEqual(len(products), 50)
        self.assertEqual(button, f'{self.category_path}/page/2')

        last_products, button = self._shop_page(button)
        self.assertEqual(len(last_products), 1)
        self.assertFalse(button, "No more products")
        self.assertEqual(set(products + last_products), set(self.products.ids))

    def test_shop_page_keeps_filters(self):
        self.env['website'].get_current_website().shop_ppr = 4
        products, button = self._shop_page(f'{self.category_path}?order=name+desc')
        self.assertEqual(products, self.products.sorted('name', reverse=True)[:48].ids)
        self.assertEqual(button, f'{self.category_path}/page/2?order=name+desc')

        self.assertEqual(self._shop_page(f'{self.category_path}?search=Show+More+05'), ([self.products[4].id], None))

    def test_tour(self):
        website = self.env['website'].get_current_website()
        website.shop_ppr = 2
        website.shop_ppg = 4
        self.products[10:].unlink()
        self.start_tour(self.category_path, 'website_sale_shop_show_more')
