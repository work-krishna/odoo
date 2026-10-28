import json
import re
from html import unescape

from odoo.exceptions import ValidationError
from odoo.fields import Command
from odoo.tests import HttpCase, tagged

from odoo.addons.website_sale.tests.common import MockRequest
from odoo.addons.website_sale_stock.tests.common import WebsiteSaleStockCommon

ATTRIBUTE_EXCLUSIONS = re.compile(r'data-attribute-exclusions="([^"]*)"')
PRODUCT_ID = re.compile(r'class="o_not_editable product_id" name="product_id" value="(\d+)"')


class VariantAvailabilityCommon(HttpCase, WebsiteSaleStockCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.color, cls.storage = cls.env['product.attribute'].create([{
            'name': 'Color', 'display_type': 'color',
            'value_ids': [Command.create({'name': name, 'html_color': html_color}) for name, html_color in (
                ('Black', '#000000'), ('Blue', '#0000FF'), ('Red', '#FF0000'),
            )],
        }, {
            'name': 'Storage', 'display_type': 'pills',
            'value_ids': [Command.create({'name': name}) for name in ('128 GB', '256 GB')],
        }])
        # Its own category, so the shop's page only has this product
        cls.category = cls.env['product.public.category'].create({'name': 'Variant Availability'})
        cls.phone = cls._create_template('Phone', cls.color.value_ids, cls.storage.value_ids)
        cls.phone.public_categ_ids = cls.category
        cls._set_stocks(cls.phone, {
            ('Black', '128 GB'): 10, ('Black', '256 GB'): 4,
            ('Blue', '128 GB'): 7, ('Blue', '256 GB'): 2,
            ('Red', '128 GB'): 0, ('Red', '256 GB'): 0,
        })

    @classmethod
    def _create_template(cls, name, *attribute_values):
        """ A published product, whose stock is tracked and which isn't sold out of stock """
        return cls.env['product.template'].create({
            'name': name,
            'list_price': 100,
            'is_storable': True,
            'allow_out_of_stock_order': False,
            'website_published': True,
            'attribute_line_ids': [
                Command.create({'attribute_id': values.attribute_id.id, 'value_ids': [Command.set(values.ids)]})
                for values in attribute_values
            ],
        })

    @classmethod
    def _variant(cls, template, *names):
        return template.product_variant_ids.filtered(
            lambda variant: sorted(variant.product_template_attribute_value_ids.mapped('name')) == sorted(names)
        )

    @classmethod
    def _ptavs(cls, template, *names):
        return template.attribute_line_ids.product_template_value_ids.filtered(lambda ptav: ptav.name in names)

    @classmethod
    def _set_stocks(cls, template, quantities):
        """ Set the on hand quantity of the variants, given by the names of their attribute values """
        for names, quantity in quantities.items():
            variant = cls._variant(template, *names)
            if quantity != variant.qty_available:
                cls.env['stock.quant']._update_available_quantity(
                    variant, cls.warehouse.lot_stock_id, quantity - variant.qty_available,
                )
        cls.env.invalidate_all()

    def _combinations(self, combinations):
        return {frozenset(combination) for combination in combinations}

    def _sold_out(self, template, *combinations):
        """ The expected sold-out combinations, from the names of their values """
        return {frozenset(self._ptavs(template, *names).ids) for names in combinations}

    def _product_page(self, template, **params):
        html = self.url_open(template.website_url, params=params).text
        exclusions = json.loads(unescape(ATTRIBUTE_EXCLUSIONS.search(html).group(1)))
        return int(PRODUCT_ID.search(html).group(1)), exclusions


@tagged('post_install', '-at_install')
class TestVariantAvailability(VariantAvailabilityCommon):

    def test_stock_is_kept_per_variant(self):
        """ Odoo keeps the stock of each variant: nothing of this module's own """
        self.assertEqual(self._variant(self.phone, 'Black', '128 GB').qty_available, 10)
        self.assertEqual(self._variant(self.phone, 'Blue', '256 GB').qty_available, 2)
        self.assertEqual(self._variant(self.phone, 'Red', '256 GB').qty_available, 0)
        self.assertEqual(self.phone.qty_available, 23)

    def test_product_page_grays_out_sold_out_combinations(self):
        product_id, exclusions = self._product_page(self.phone)
        self.assertEqual(product_id, self._variant(self.phone, 'Black', '128 GB').id)
        self.assertEqual(
            self._combinations(exclusions['archived_combinations']),
            self._sold_out(self.phone, ('Red', '128 GB'), ('Red', '256 GB')),
        )

        # Sold out after an order: gone from the free quantity
        self._set_stocks(self.phone, {('Blue', '256 GB'): 0})
        _product_id, exclusions = self._product_page(self.phone)
        self.assertEqual(
            self._combinations(exclusions['archived_combinations']),
            self._sold_out(self.phone, ('Red', '128 GB'), ('Red', '256 GB'), ('Blue', '256 GB')),
        )

    def test_archived_variants_stay_grayed_out(self):
        self._variant(self.phone, 'Blue', '128 GB').action_archive()
        _product_id, exclusions = self._product_page(self.phone)
        self.assertEqual(
            self._combinations(exclusions['archived_combinations']),
            self._sold_out(self.phone, ('Red', '128 GB'), ('Red', '256 GB'), ('Blue', '128 GB')),
        )

    def test_three_attributes_and_variants_created_later(self):
        size, material = self.env['product.attribute'].create([{
            'name': 'Size', 'display_type': 'radio',
            'value_ids': [Command.create({'name': name}) for name in ('S', 'M', 'L', 'XL')],
        }, {
            'name': 'Material', 'display_type': 'select',
            'value_ids': [Command.create({'name': name}) for name in ('Cotton', 'Polyester')],
        }])
        black, blue, red = self.color.value_ids
        tshirt = self._create_template('T-Shirt', red | blue, size.value_ids, material.value_ids)
        self.assertEqual(len(tshirt.product_variant_ids), 16)
        self._set_stocks(tshirt, {
            (color, size_name, material_name): 5
            for color in ('Red', 'Blue') for size_name in ('S', 'M', 'L', 'XL') for material_name in ('Cotton', 'Polyester')
            if (color, size_name) != ('Red', 'M') and (color, size_name, material_name) != ('Blue', 'S', 'Cotton')
        })
        sold_out = [('Red', 'M', 'Cotton'), ('Red', 'M', 'Polyester'), ('Blue', 'S', 'Cotton')]
        self.assertEqual(
            self._combinations(tshirt._get_sold_out_combinations()), self._sold_out(tshirt, *sold_out),
        )
        _product_id, exclusions = self._product_page(tshirt)
        self.assertEqual(self._combinations(exclusions['archived_combinations']), self._sold_out(tshirt, *sold_out))

        # A color added later: its variants have no stock yet
        tshirt.attribute_line_ids.filtered(lambda ptal: ptal.attribute_id == self.color).value_ids += black
        self.assertEqual(len(tshirt.product_variant_ids), 24)
        sold_out += [('Black', size_name, material_name) for size_name in ('S', 'M', 'L', 'XL') for material_name in ('Cotton', 'Polyester')]
        self.assertEqual(self._combinations(tshirt._get_sold_out_combinations()), self._sold_out(tshirt, *sold_out))

        # Received
        self._set_stocks(tshirt, {('Black', 'L', 'Cotton'): 3})
        sold_out.remove(('Black', 'L', 'Cotton'))
        self.assertEqual(self._combinations(tshirt._get_sold_out_combinations()), self._sold_out(tshirt, *sold_out))

    def test_only_products_not_sold_out_of_stock(self):
        self.phone.allow_out_of_stock_order = True
        self.assertEqual(self.phone._get_sold_out_combinations(), [])
        _product_id, exclusions = self._product_page(self.phone)
        self.assertEqual(exclusions['archived_combinations'], [])

        self.phone.write({'allow_out_of_stock_order': False, 'is_storable': False})
        self.assertEqual(self.phone._get_sold_out_combinations(), [])

    def test_product_page_opens_on_a_variant_in_stock(self):
        self._set_stocks(self.phone, {('Black', '128 GB'): 0})
        product_id, exclusions = self._product_page(self.phone)
        self.assertEqual(product_id, self._variant(self.phone, 'Black', '256 GB').id)
        self.assertEqual(
            self._combinations(exclusions['archived_combinations']),
            self._sold_out(self.phone, ('Black', '128 GB'), ('Red', '128 GB'), ('Red', '256 GB')),
        )

        # Unless the URL asks for a variant
        attribute_values = self._ptavs(self.phone, 'Black', '128 GB').product_attribute_value_id
        product_id, _exclusions = self._product_page(self.phone, attribute_values=','.join(map(str, attribute_values.ids)))
        self.assertEqual(product_id, self._variant(self.phone, 'Black', '128 GB').id)

        self._set_stocks(self.phone, {('Black', '256 GB'): 0, ('Blue', '128 GB'): 0})
        product_id, _exclusions = self._product_page(self.phone)
        self.assertEqual(product_id, self._variant(self.phone, 'Blue', '256 GB').id)

        # All sold out: Odoo's first variant
        self._set_stocks(self.phone, {('Blue', '256 GB'): 0})
        product_id, _exclusions = self._product_page(self.phone)
        self.assertEqual(product_id, self._variant(self.phone, 'Black', '128 GB').id)

    def test_shop_out_of_stock_only_when_all_variants_are(self):
        ribbon = self.env.ref('website_sale.out_of_stock_ribbon')
        ribbon.assign = 'out_of_stock'
        shop_url = f"/shop/category/{self.env['ir.http']._slug(self.category)}"
        out_of_stock_ribbon = f'data-ribbon-id="{ribbon.id}"'

        self.assertNotIn(out_of_stock_ribbon, self.url_open(shop_url).text)
        # Its first variant
        self._set_stocks(self.phone, {('Black', '128 GB'): 0})
        self.assertTrue(self._variant(self.phone, 'Black', '128 GB')._is_sold_out())
        self.assertFalse(self.phone._is_sold_out())
        self.assertNotIn(out_of_stock_ribbon, self.url_open(shop_url).text)

        self._set_stocks(self.phone, {('Black', '256 GB'): 0, ('Blue', '128 GB'): 0, ('Blue', '256 GB'): 0})
        self.assertTrue(self.phone._is_sold_out())
        self.assertIn(out_of_stock_ribbon, self.url_open(shop_url).text)

    def test_sold_out_variant_cannot_be_bought(self):
        """ Odoo refuses the out-of-stock variants in the cart, whatever the variant picker shows """
        red_128, blue_256 = self._variant(self.phone, 'Red', '128 GB'), self._variant(self.phone, 'Blue', '256 GB')
        cart = self.empty_cart
        with MockRequest(self.env, website=self.website, sale_order_id=cart.id):
            values = cart._cart_add(product_id=red_128.id, quantity=1)
            self.assertEqual(values['quantity'], 0)
            self.assertFalse(cart.order_line)

            values = cart._cart_add(product_id=blue_256.id, quantity=5)
            self.assertEqual(values['quantity'], 2)
            self.assertEqual(cart.order_line.product_id, blue_256)
            self.assertEqual(cart.order_line.product_uom_qty, 2)

    def test_variant_marked_out_of_stock_whatever_its_quantity(self):
        blue_128 = self._variant(self.phone, 'Blue', '128 GB')
        blue_128.is_variant_out_of_stock = True
        self.assertEqual(blue_128.qty_available, 7)
        self.assertTrue(blue_128._is_sold_out())
        self.assertEqual(
            self._combinations(self.phone._get_sold_out_combinations()),
            self._sold_out(self.phone, ('Red', '128 GB'), ('Red', '256 GB'), ('Blue', '128 GB')),
        )

    def test_variant_picker_tour(self):
        self._set_stocks(self.phone, {('Black', '128 GB'): 0})
        self.start_tour(self.phone.website_url, 'website_sale_stock_variant_availability')


@tagged('post_install', '-at_install')
class TestVariantAvailabilityMobile(VariantAvailabilityCommon):
    browser_size = '375x667'
    touch_enabled = True

    def test_variant_picker_tour(self):
        self._set_stocks(self.phone, {('Black', '128 GB'): 0})
        self.start_tour(self.phone.website_url, 'website_sale_stock_variant_availability')


@tagged('post_install', '-at_install')
class TestVariantMarkedOutOfStock(HttpCase, WebsiteSaleStockCommon):
    """ The variants marked out of stock by hand, of a product whose inventory isn't tracked """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.color, cls.storage = cls.env['product.attribute'].create([{
            'name': 'Color', 'display_type': 'color',
            'value_ids': [Command.create({'name': name, 'html_color': html_color}) for name, html_color in (
                ('Black', '#000000'), ('Blue', '#0000FF'), ('Red', '#FF0000'),
            )],
        }, {
            'name': 'Storage', 'display_type': 'pills',
            'value_ids': [Command.create({'name': name}) for name in ('128 GB', '256 GB')],
        }])
        cls.category = cls.env['product.public.category'].create({'name': 'Marked Out of Stock'})
        cls.phone = cls.env['product.template'].create({
            'name': 'Marked Phone', 'list_price': 100, 'is_storable': False, 'website_published': True,
            'public_categ_ids': [Command.set(cls.category.ids)],
            'attribute_line_ids': [
                Command.create({'attribute_id': attribute.id, 'value_ids': [Command.set(attribute.value_ids.ids)]})
                for attribute in (cls.color, cls.storage)
            ],
        })
        cls.ribbon = cls.env.ref('website_sale.out_of_stock_ribbon')
        cls.ribbon.assign = 'out_of_stock'

    def _variant(self, *names):
        return self.phone.product_variant_ids.filtered(
            lambda variant: sorted(variant.product_template_attribute_value_ids.mapped('name')) == sorted(names)
        )

    def _product_page(self, variant=None):
        params = {}
        if variant:
            params['attribute_values'] = ','.join(map(str, variant.product_template_attribute_value_ids.product_attribute_value_id.ids))
        html = self.url_open(self.phone.website_url, params=params).text
        exclusions = json.loads(unescape(ATTRIBUTE_EXCLUSIONS.search(html).group(1)))
        return int(PRODUCT_ID.search(html).group(1)), exclusions, html

    def _combination_info(self, variant):
        return self.make_jsonrpc_request('/website_sale/get_combination_info', {
            'product_template_id': self.phone.id, 'product_id': 0,
            'combination': variant.product_template_attribute_value_ids.ids, 'add_qty': 1,
        })

    def test_marked_variant_is_out_of_stock(self):
        red_128 = self._variant('Red', '128 GB')
        red_128.is_variant_out_of_stock = True
        self.assertTrue(red_128._is_sold_out())
        self.assertFalse(self.phone._is_sold_out())

        product_id, exclusions, html = self._product_page()
        self.assertEqual(product_id, self._variant('Black', '128 GB').id)
        self.assertEqual(exclusions['archived_combinations'], [red_128.product_template_attribute_value_ids.ids])
        self.assertNotIn(f'data-ribbon-id="{self.ribbon.id}"', html)

        info = self._combination_info(red_128)
        self.assertEqual((info['is_storable'], info['allow_out_of_stock_order'], info['free_qty']), (True, False, 0))
        self.assertNotIn('free_qty', self._combination_info(self._variant('Red', '256 GB')), "Not tracked")

        # Its product page, from a link to it
        _product_id, _exclusions, html = self._product_page(red_128)
        self.assertIn(f'data-ribbon-id="{self.ribbon.id}"', html)

        # Opens on a variant that isn't
        self._variant('Black', '128 GB').is_variant_out_of_stock = True
        self.assertEqual(self._product_page()[0], self._variant('Black', '256 GB').id)

    def test_marked_variant_cannot_be_bought(self):
        red_128, blue_128 = self._variant('Red', '128 GB'), self._variant('Blue', '128 GB')
        red_128.is_variant_out_of_stock = True
        cart = self.empty_cart
        with MockRequest(self.env, website=self.website, sale_order_id=cart.id):
            self.assertEqual(cart._cart_add(product_id=red_128.id, quantity=1)['quantity'], 0)
            self.assertFalse(cart.order_line)
            cart._cart_add(product_id=blue_128.id, quantity=2)
            self.assertEqual(cart.order_line.product_uom_qty, 2)

            # Marked once in the cart
            blue_128.is_variant_out_of_stock = True
            with self.assertRaises(ValidationError):
                cart._check_cart_is_ready_to_be_paid()

        values = self.make_jsonrpc_request('/website_sale/product_configurator/get_values', {
            'product_template_id': self.phone.id, 'quantity': 1, 'currency_id': self.phone.currency_id.id,
            'so_date': '2026-01-01 00:00:00', 'ptav_ids': red_128.product_template_attribute_value_ids.ids,
        })['products'][0]
        self.assertEqual(values['free_qty'], 0)

    def test_shop_out_of_stock_when_all_variants_are(self):
        shop_url = f"/shop/category/{self.env['ir.http']._slug(self.category)}"
        out_of_stock_ribbon = f'data-ribbon-id="{self.ribbon.id}"'
        self._variant('Black', '128 GB').is_variant_out_of_stock = True
        self.assertNotIn(out_of_stock_ribbon, self.url_open(shop_url).text)
        self.phone.product_variant_ids.is_variant_out_of_stock = True
        self.assertTrue(self.phone._is_sold_out())
        self.assertIn(out_of_stock_ribbon, self.url_open(shop_url).text)

    def test_marked_variant_tour(self):
        self._variant('Red', '128 GB').is_variant_out_of_stock = True
        self.start_tour(self.phone.website_url, 'website_sale_stock_variant_marked_out_of_stock')

    def test_variant_list_toggle_tour(self):
        self.start_tour(
            '/odoo/action-product.product_normal_action_sell?view_type=list',
            'website_sale_stock_variant_marked_out_of_stock_list', login='admin',
        )
        self.assertEqual(
            self.phone.product_variant_ids.filtered('is_variant_out_of_stock'), self._variant('Red', '128 GB'),
        )
