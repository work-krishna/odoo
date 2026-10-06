from lxml import html

from odoo.fields import Command
from odoo.tests import tagged

from odoo.addons.website_sale.tests.common import MockRequest, WebsiteSaleCommon
from odoo.addons.website_sale_vat_included_total.controllers.delivery import (
    WebsiteSaleVatIncludedTotalDelivery,
)


@tagged('post_install', '-at_install')
class TestVatIncludedTotalLoyalty(WebsiteSaleCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.website.show_line_subtotals_tax_selection = 'tax_included'
        cls.env['loyalty.program'].search([]).action_archive()
        cls.vat_13 = cls.env['account.tax'].create({'name': "VAT 13%", 'amount': 13})
        cls.product.write({'list_price': 1000, 'taxes_id': [Command.set(cls.vat_13.ids)]})
        cls.charger = cls._create_product(
            name="Untaxed Charger", list_price=100, taxes_id=[Command.clear()],
        )
        cls.courier = cls._prepare_carrier(
            cls._prepare_carrier_product(taxes_id=[Command.set(cls.vat_13.ids)]),
            name="Courier", fixed_price=100,
        )
        cls.voucher = cls.env['loyalty.program'].create({
            'name': "Dashain Voucher",
            'program_type': 'promo_code',
            'trigger': 'with_code',
            'rule_ids': [Command.create({'code': 'DASHAIN500'})],
            'reward_ids': [Command.create({
                'reward_type': 'discount',
                'discount': 500,
                'discount_mode': 'per_order',
                'discount_applicability': 'order',
                'description': "Dashain Voucher",
            })],
        })
        cls.free_shipping = cls.env['loyalty.program'].create({
            'name': "Free Shipping",
            'program_type': 'promotion',
            'trigger': 'auto',
            'rule_ids': [Command.create({})],
            'reward_ids': [Command.create({
                'reward_type': 'shipping', 'description': "Shipping discount",
            })],
        })

    def _cart_with_vouchers(self):
        """1130 (1000 + VAT) + 100 untaxed + 113 delivery (100 + VAT), less the 500 voucher and
        the free shipping: 730."""
        cart = self._create_so(order_line=[
            Command.create({'product_id': self.product.id}),
            Command.create({'product_id': self.charger.id}),
        ])
        self._visit_cart(cart)
        cart._set_delivery_method(self.courier)
        for coupon, rewards in cart._try_apply_code('DASHAIN500').items():
            cart._apply_program_reward(rewards, coupon)
        self.assertEqual(cart.amount_total, 730)
        return cart

    @staticmethod
    def _visit_cart(cart):
        """Claim the rewards to claim automatically, the free shipping, as visiting the cart does."""
        cart._update_programs_and_rewards()
        cart._auto_apply_rewards()

    def _render(self, template, cart):
        with MockRequest(self.env, website=self.website, sale_order_id=cart.id):
            rendered = self.env['ir.ui.view']._render_template(template, {
                'website_sale_order': cart, 'hide_promotions': True,
            })
        return html.fromstring(str(rendered))

    @staticmethod
    def _rows(order_detail):
        """[(row name, text)] of the summary's Order Detail table, the hidden rows left out."""
        return [
            (row.get('name'), ' '.join(row.text_content().replace('\ufeff', '').split()))
            for row in order_detail.xpath('//table[@name="o_order_detail"]//tr')
            if 'd-none' not in row.classes
        ]

    def test_vouchers_rows_between_delivery_fee_and_total(self):
        cart = self._cart_with_vouchers()
        rows = self._rows(self._render('website_sale.total', cart))
        self.assertEqual(
            [name for name, _text in rows],
            ['o_order_items_total', 'o_order_delivery', 'o_order_reward', 'o_order_reward',
             'o_order_total'],
        )
        self.assertIn("Items Total (2 Items)", rows[0][1], "the vouchers are not items")
        self.assertIn('1,230.00', rows[0][1], "the items at their own price")
        self.assertIn('113.00', rows[1][1])
        self.assertIn("Shipping discount", rows[2][1], "the reward's description")
        self.assertNotIn("Free Shipping -", rows[2][1])
        self.assertIn('-113.00', rows[2][1])
        self.assertIn("Dashain Voucher", rows[3][1])
        self.assertIn('-500.00', rows[3][1], "the voucher's amount, tax included")
        self.assertIn('730.00', rows[4][1])
        self.assertEqual(
            cart._get_items_total() + cart.amount_delivery
            + sum(line._get_cart_display_price() for line in cart._get_summary_reward_lines()),
            cart.amount_total,
        )

    def test_vouchers_not_listed_with_the_items(self):
        cart = self._cart_with_vouchers()
        summary = self._render('website_sale.cart_summary_content', cart)
        lines = summary.xpath('//table[hasclass("o_cart_products_table")]//tr')
        listed = [' '.join(tr.text_content().split()) for tr in lines if 'd-none' not in tr.classes]
        self.assertEqual(len(listed), 2)
        self.assertIn("Untaxed Charger", listed[-1])
        self.assertIn('border-transparent', [tr for tr in lines if 'd-none' not in tr.classes][-1].classes)
        self.assertFalse(
            summary.xpath('//div[hasclass("o_wsale_scrollable_table")]'),
            "2 items shown: no scrolling, which takes a fixed height",
        )
        hidden = [tr for tr in lines if 'd-none' in tr.classes]
        self.assertEqual(len(hidden), 2)
        self.assertTrue(
            [tr for tr in hidden if tr.xpath('.//*[@data-reward-type="discount"]')],
            "kept in the page for the checkout of website_sale_loyalty, which counts them",
        )

    def test_tax_excluded_website_lists_vouchers_with_the_items(self):
        self.website.show_line_subtotals_tax_selection = 'tax_excluded'
        cart = self._cart_with_vouchers()
        self.assertFalse(cart._get_summary_reward_lines())
        lines = self._render('website_sale.cart_summary_content', cart).xpath(
            '//table[hasclass("o_cart_products_table")]//tr'
        )
        self.assertEqual(len(lines), 4)
        self.assertFalse([tr for tr in lines if 'd-none' in tr.classes])

    def test_delivery_method_change_renders_free_shipping(self):
        cart = self._create_so(order_line=[Command.create({'product_id': self.product.id})])
        self._visit_cart(cart)
        self.assertNotIn('o_order_reward', [name for name, _text in self._rows(
            self._render('website_sale.total', cart)
        )], "no free shipping row before a delivery method is chosen")
        with MockRequest(self.env, website=self.website, sale_order_id=cart.id) as request:
            request.cart = cart
            values = WebsiteSaleVatIncludedTotalDelivery().shop_set_delivery_method(
                dm_id=self.courier.id,
            )
        rows = self._rows(html.fromstring(values['order_detail']))
        self.assertEqual(
            [name for name, _text in rows],
            ['o_order_items_total', 'o_order_delivery', 'o_order_reward', 'o_order_total'],
        )
        self.assertIn('1,130.00', rows[-1][1])
