from lxml import html

from odoo.fields import Command
from odoo.tests import HttpCase, tagged

from odoo.addons.website_sale.tests.common import MockRequest, WebsiteSaleCommon
from odoo.addons.website_sale_vat_included_total.controllers.delivery import (
    WebsiteSaleVatIncludedTotalDelivery,
)


@tagged('post_install', '-at_install')
class TestVatIncludedTotal(WebsiteSaleCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.website.show_line_subtotals_tax_selection = 'tax_included'
        cls.vat_13, cls.vat_5 = cls.env['account.tax'].create([
            {'name': "VAT 13%", 'amount': 13},
            {'name': "VAT 5%", 'amount': 5},
        ])
        # Taxes set on every product, so the company's default sale tax plays no part
        cls.product.write({'list_price': 1000, 'taxes_id': [Command.set(cls.vat_13.ids)]})
        cls.service_product.write({'list_price': 200, 'taxes_id': [Command.set(cls.vat_5.ids)]})
        cls.untaxed_product = cls._create_product(
            name="Untaxed Charger", list_price=100, taxes_id=[Command.clear()],
        )
        cls.free_pickup = cls._prepare_carrier(
            cls._prepare_carrier_product(taxes_id=[Command.clear()]), name="Pickup", fixed_price=0,
        )
        cls.courier = cls._prepare_carrier(
            cls._prepare_carrier_product(taxes_id=[Command.set(cls.vat_13.ids)]),
            name="Courier", fixed_price=100,
        )

    def _cart(self, *products):
        return self._create_so(order_line=[
            Command.create({'product_id': product.id}) for product in products
        ])

    def _render_summary(self, cart, hide_promotions=True):
        with MockRequest(self.env, website=self.website, sale_order_id=cart.id):
            rendered = self.env['ir.ui.view']._render_template('website_sale.total', {
                'website_sale_order': cart, 'hide_promotions': hide_promotions,
            })
        return html.fromstring(str(rendered))

    def _shown(self, cart):
        """{name: whether it is shown} for the rows of the cart's order summary, and its
        'o_order_total_tax_note'."""
        return {
            element.get('name'): 'd-none' not in element.classes
            for element in self._render_summary(cart).xpath('//*[@name]')
        }

    @staticmethod
    def _text(summary, name):
        [element] = summary.xpath(f'//*[@name="{name}"]')
        return ' '.join(element.text_content().split())

    def test_order_detail_instead_of_subtotal_and_taxes(self):
        cart = self._cart(self.product)
        self.assertEqual(
            (cart.amount_untaxed, cart.amount_tax, cart.amount_total), (1000, 130, 1130),
            "the order still records its tax",
        )
        summary = self._render_summary(cart)
        shown = self._shown(cart)
        self.assertFalse(shown['o_order_total_untaxed'])
        self.assertFalse(shown['o_order_total_taxes'])
        self.assertTrue(shown['o_order_items_total'])
        self.assertTrue(shown['o_order_delivery'])
        self.assertTrue(shown['o_order_total'])
        self.assertTrue(shown['o_order_total_tax_note'])
        self.assertIn("Order Detail", summary.text_content())
        self.assertIn("Items Total (1 Item)", self._text(summary, 'o_order_items_total'))
        self.assertIn('1,130.00', self._text(summary, 'o_order_items_total'))
        self.assertIn("Delivery Fee", self._text(summary, 'o_order_delivery'))
        self.assertIn('1,130.00', self._text(summary, 'o_order_total'))
        [amount] = summary.xpath('//tr[@name="o_order_total"]//strong[hasclass("monetary_field")]')
        self.assertIn('text-primary', amount.classes)
        self.assertEqual(self._text(summary, 'o_order_total_tax_note'), "All taxes included")
        self.assertIn('small', summary.xpath('//*[@name="o_order_total_tax_note"]')[0].classes)

    def test_amounts_still_updatable_by_the_checkout(self):
        """The checkout's script updates the amounts it finds by these selectors when the delivery
        method changes."""
        summary = self._render_summary(self._cart(self.product))
        for row in ('o_order_delivery', 'o_order_total_untaxed', 'o_order_total_taxes',
                    'o_order_total', 'o_order_items_total'):
            self.assertTrue(
                summary.xpath(f'//tr[@name="{row}"]//*[hasclass("monetary_field")]'), row,
            )

    def test_items_total_adds_up_with_delivery_fee(self):
        cart = self._create_so(order_line=[
            Command.create({'product_id': self.product.id, 'product_uom_qty': 2}),
            Command.create({'product_id': self.untaxed_product.id}),
        ])
        cart._set_delivery_method(self.courier)
        self.assertEqual(
            (cart._get_items_total(), cart.amount_delivery, cart.amount_total), (2360, 113, 2473),
        )
        summary = self._render_summary(cart)
        self.assertIn("Items Total (3 Items)", self._text(summary, 'o_order_items_total'))
        self.assertIn('2,360.00', self._text(summary, 'o_order_items_total'))
        self.assertIn('113.00', self._text(summary, 'o_order_delivery'))
        self.assertIn('2,473.00', self._text(summary, 'o_order_total'))

    def test_promotion_above_order_detail(self):
        text = self._render_summary(self._cart(self.product), hide_promotions=False).text_content()
        self.assertLess(text.index("Promotion"), text.index("Order Detail"))
        self.assertLess(text.index("Order Detail"), text.index("Items Total"))

    def test_no_note_without_tax(self):
        cart = self._cart(self.untaxed_product)
        self.assertFalse(cart.amount_tax)
        shown = self._shown(cart)
        self.assertFalse(shown['o_order_total_untaxed'])
        self.assertFalse(shown['o_order_total_taxes'])
        self.assertFalse(shown['o_order_total_tax_note'])

    def test_note_with_several_rates_and_untaxed_products(self):
        cart = self._cart(self.product, self.service_product, self.untaxed_product)
        self.assertEqual((cart.amount_tax, cart.amount_total), (140, 1440))
        self.assertTrue(self._shown(cart)['o_order_total_tax_note'])

    def test_note_with_tax_included_prices(self):
        vat_13_included = self.env['account.tax'].create({
            'name': "VAT 13% included", 'amount': 13, 'price_include_override': 'tax_included',
        })
        self.product.write({'list_price': 1130, 'taxes_id': [Command.set(vat_13_included.ids)]})
        cart = self._cart(self.product)
        self.assertEqual((cart.amount_tax, cart.amount_total), (130, 1130))
        self.assertTrue(self._shown(cart)['o_order_total_tax_note'])

    def test_no_note_when_fiscal_position_removes_the_tax(self):
        self.env.company.country_id = self.env.ref('base.np')
        # A new fiscal country resets the website's tax display
        self.website.show_line_subtotals_tax_selection = 'tax_included'
        export = self.env['account.fiscal.position'].create({
            'name': "Export", 'auto_apply': True, 'country_id': self.country_us.id,
        })
        vat_0 = self.env['account.tax'].create({
            'name': "VAT 0% export", 'amount': 0, 'fiscal_position_ids': export.ids,
        })
        vat_0.original_tax_ids = self.vat_13
        self.partner.country_id = self.country_us
        cart = self._cart(self.product)
        self.assertEqual(cart.fiscal_position_id, export)
        self.assertEqual(cart.order_line.tax_ids, vat_0)
        self.assertFalse(cart.amount_tax)
        self.assertFalse(self._shown(cart)['o_order_total_tax_note'])

    def test_tax_excluded_website_keeps_the_breakdown(self):
        self.website.show_line_subtotals_tax_selection = 'tax_excluded'
        cart = self._cart(self.product)
        summary = self._render_summary(cart)
        shown = self._shown(cart)
        self.assertTrue(shown['o_order_total_untaxed'])
        self.assertTrue(shown['o_order_total_taxes'])
        self.assertTrue(shown['o_order_total'])
        self.assertNotIn('o_order_items_total', shown)
        self.assertNotIn('o_order_total_tax_note', shown)
        self.assertNotIn("Order Detail", summary.text_content())
        self.assertEqual(self._text(summary, 'o_order_delivery').split()[0], "Delivery")
        [detail] = summary.xpath('//table[@name="o_order_detail"]')
        self.assertIn('order-first', detail.classes, "the totals stay above the promo code")
        [amount] = summary.xpath('//tr[@name="o_order_total"]//strong[hasclass("monetary_field")]')
        self.assertNotIn('text-primary', amount.classes)

    def test_delivery_method_change_renders_order_detail(self):
        cart = self._cart(self.untaxed_product)
        with MockRequest(self.env, website=self.website, sale_order_id=cart.id) as request:
            request.cart = cart
            controller = WebsiteSaleVatIncludedTotalDelivery()
            detail = html.fromstring(
                controller.shop_set_delivery_method(dm_id=self.courier.id)['order_detail'],
            )
            self.assertEqual(cart.amount_tax, 13)
            self.assertIn('100.00', self._text(detail, 'o_order_items_total'))
            self.assertIn('113.00', self._text(detail, 'o_order_delivery'))
            self.assertIn('213.00', self._text(detail, 'o_order_total'))
            [note] = detail.xpath('//*[@name="o_order_total_tax_note"]')
            self.assertNotIn('d-none', note.classes)

            detail = html.fromstring(
                controller.shop_set_delivery_method(dm_id=self.free_pickup.id)['order_detail'],
            )
            self.assertFalse(cart.amount_tax)
            self.assertIn('100.00', self._text(detail, 'o_order_total'))
            [note] = detail.xpath('//*[@name="o_order_total_tax_note"]')
            self.assertIn('d-none', note.classes)

    def test_tax_excluded_delivery_change_keeps_core_values(self):
        self.website.show_line_subtotals_tax_selection = 'tax_excluded'
        cart = self._cart(self.untaxed_product)
        with MockRequest(self.env, website=self.website, sale_order_id=cart.id) as request:
            request.cart = cart
            values = WebsiteSaleVatIncludedTotalDelivery().shop_set_delivery_method(
                dm_id=self.courier.id,
            )
        self.assertNotIn('order_detail', values)
        self.assertIn('213.00', values['amount_total'])


@tagged('post_install', '-at_install')
class TestVatIncludedTotalUi(HttpCase):

    def test_note_follows_delivery_method(self):
        website = self.env.ref('website.default_website')
        website.show_line_subtotals_tax_selection = 'tax_included'
        # No discount from a demo pricelist, so the tour can check the totals
        self.env['product.pricelist'].search([]).action_archive()
        self.env['product.pricelist'].create({'name': "Public", 'website_id': website.id})
        vat_13 = self.env['account.tax'].create({'name': "VAT 13%", 'amount': 13})
        # Skips the address step of the checkout
        self.env.ref('base.partner_admin').write({
            'street': '215 Vine St',
            'city': 'Scranton',
            'zip': '18503',
            'country_id': self.env.ref('base.us').id,
            'state_id': self.env.ref('base.state_us_39').id,
            'phone': '+1 555-555-5555',
            'email': 'admin@yourcompany.example.com',
        })
        self.env['product.product'].create({
            'name': "Untaxed Charger",
            'type': 'consu',
            'list_price': 100,
            'taxes_id': [Command.clear()],
            'is_published': True,
        })
        self.env['delivery.carrier'].search([]).action_archive()
        for name, price, taxes in [("Free Pickup", 0, []), ("Courier with VAT", 100, vat_13.ids)]:
            self.env['delivery.carrier'].create({
                'name': name,
                'delivery_type': 'fixed',
                'fixed_price': price,
                'website_published': True,
                'product_id': self.env['product.product'].create({
                    'name': name,
                    'type': 'service',
                    'categ_id': self.env.ref('delivery.product_category_deliveries').id,
                    'sale_ok': False,
                    'list_price': price,
                    'taxes_id': [Command.set(taxes)],
                }).id,
            })
        self.start_tour('/', 'website_sale_vat_included_total_delivery', login='admin')
