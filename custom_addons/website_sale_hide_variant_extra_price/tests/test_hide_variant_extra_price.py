import re

from odoo.fields import Command
from odoo.tests import HttpCase, tagged

from odoo.addons.website_sale.tests.common import MockRequest, WebsiteSaleCommon

PRICE = re.compile(r'class="oe_price"[^>]*>.*?<span class="oe_currency_value">([^<]*)</span>', re.S)


@tagged('post_install', '-at_install')
class TestHideVariantExtraPrice(HttpCase, WebsiteSaleCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        memory, color, material, finish, strap = cls.env['product.attribute'].create([{
            'name': 'RAM/ROM', 'display_type': 'radio',
            'value_ids': [Command.create({'name': '8GB/256GB'}), Command.create({'name': '12GB/256GB'})],
        }, {
            'name': 'Color', 'display_type': 'color',
            'value_ids': [Command.create({'name': 'Sunrise Gold', 'html_color': '#D4AF37'}), Command.create({'name': 'Midnight Black', 'html_color': '#000000'})],
        }, {
            'name': 'Material', 'display_type': 'pills',
            'value_ids': [Command.create({'name': 'Silicone'}), Command.create({'name': 'Leather'})],
        }, {
            'name': 'Finish', 'display_type': 'select',
            'value_ids': [Command.create({'name': 'Matte'}), Command.create({'name': 'Glossy'})],
        }, {
            'name': 'Strap', 'display_type': 'multi', 'create_variant': 'no_variant',
            'value_ids': [Command.create({'name': 'Lanyard'})],
        }])
        cls.case, cls.phone = cls.env['product.template'].create([{
            'name': 'Case', 'list_price': 10,
            'attribute_line_ids': [
                Command.create({'attribute_id': attribute.id, 'value_ids': [Command.set(attribute.value_ids.ids)]})
                for attribute in (material, finish, strap)
            ],
        }, {
            'name': 'Phone', 'list_price': 100,
            'attribute_line_ids': [
                Command.create({'attribute_id': attribute.id, 'value_ids': [Command.set(attribute.value_ids.ids)]})
                for attribute in (memory, color, finish)
            ],
        }])
        (cls.case | cls.phone).write({'website_published': True, 'taxes_id': [Command.clear()]})
        cls.phone.optional_product_ids = cls.case
        for template, extra_prices in (
            (cls.phone, {'12GB/256GB': 50, 'Glossy': 3}),
            (cls.case, {'Leather': 5, 'Glossy': 3, 'Lanyard': 2}),
        ):
            for ptav in template.attribute_line_ids.product_template_value_ids:
                ptav.price_extra = extra_prices.get(ptav.name, 0)

    def _ptavs(self, template, *names):
        return template.attribute_line_ids.product_template_value_ids.filtered(lambda ptav: ptav.name in names)

    def _product_page(self, *names):
        attribute_values = self._ptavs(self.phone, *names).product_attribute_value_id
        return self.url_open(self.phone.website_url, params={
            'attribute_values': ','.join(map(str, attribute_values.ids)),
        }).text

    def test_product_page_without_extra_prices(self):
        html = self._product_page('8GB/256GB', 'Sunrise Gold', 'Matte')
        self.assertIn('12GB/256GB', html)
        self.assertNotIn('variant_price_extra', html)
        self.assertNotIn('sign_badge_price_extra', html)
        self.assertRegex(html, r'<option [^>]*data-value-name="Glossy"[^>]*>\s*<span>Glossy</span>\s*</option>')
        self.assertEqual(PRICE.search(html).group(1), '100.00')

    def test_extra_prices_still_apply(self):
        self.assertEqual(PRICE.search(self._product_page('12GB/256GB', 'Sunrise Gold', 'Matte')).group(1), '150.00')
        self.assertEqual(PRICE.search(self._product_page('12GB/256GB', 'Sunrise Gold', 'Glossy')).group(1), '153.00')

        variant = self.phone._get_variant_for_combination(self._ptavs(self.phone, '12GB/256GB', 'Midnight Black', 'Glossy'))
        cart = self.empty_cart
        with MockRequest(self.env, website=self.website, sale_order_id=cart.id):
            cart._cart_add(product_id=variant.id, quantity=2)
        self.assertEqual(cart.order_line.price_unit, 153)
        self.assertEqual(cart.amount_untaxed, 306)

    def test_hide_variant_extra_price_tour(self):
        self.start_tour(self.phone.website_url, 'website_sale_hide_variant_extra_price')
