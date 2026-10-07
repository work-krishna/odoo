from lxml import html

from odoo.fields import Command
from odoo.tests import Form, HttpCase, tagged

from odoo.addons.website_sale.tests.common import WebsiteSaleCommon


@tagged('post_install', '-at_install')
class TestSearchProductTags(HttpCase, WebsiteSaleCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.trekking, cls.waterproof, cls.damaged = cls.env['product.tag'].create([
            {'name': 'Trekking'},
            {'name': 'Waterproof'},
            {'name': 'Damaged', 'visible_to_customers': False},
        ])
        size = cls.env['product.attribute'].create({
            'name': 'Size', 'value_ids': [Command.create({'name': name}) for name in ('S', 'L')],
        })
        # Their own category, so the searches only find them
        cls.category = cls.env['product.public.category'].create({'name': 'Search Tags'})
        cls.boots, cls.mug, cls.jacket, cls.tent = cls.env['product.template'].create([{
            'name': 'Hiking Boots', 'product_tag_ids': [Command.set(cls.trekking.ids)],
        }, {
            'name': 'Trekkies Mug',
        }, {
            'name': 'Rain Jacket',
            'attribute_line_ids': [Command.create({'attribute_id': size.id, 'value_ids': [Command.set(size.value_ids.ids)]})],
        }, {
            'name': 'Dome Tent', 'product_tag_ids': [Command.set(cls.damaged.ids)],
        }])
        cls.jacket.product_variant_ids[0].additional_product_tag_ids = cls.waterproof
        (cls.boots | cls.mug | cls.jacket | cls.tent).write({
            'list_price': 100, 'website_published': True, 'public_categ_ids': [Command.set(cls.category.ids)],
        })

    def _search(self, search, allow_fuzzy=True):
        """ The products found, and the search term used when there was a typo """
        # As on the website, where the changes were saved by earlier requests:
        # with pg_trgm, the typo correction reads the products in SQL
        self.env.flush_all()
        _count, details, fuzzy_term = self.website._search_with_fuzzy('products_only', search, limit=None, order='name asc', options={
            'displayDescription': True, 'displayDetail': False, 'displayExtraLink': False, 'displayImage': False,
            'allowFuzzy': allow_fuzzy, 'category': str(self.category.id),
        })
        return details[0]['results'], fuzzy_term

    def test_search_by_tag(self):
        self.assertEqual(self._search('trekking'), (self.boots, False))
        self.assertEqual(self._search('Hiking'), (self.boots, False), "Still by name")
        self.assertEqual(self._search('trek'), (self.boots | self.mug, False), "Both, by name or tag")
        self.assertEqual(self._search('trekking boots'), (self.boots, False), "A word of the tag and one of the name")
        self.assertEqual(self._search('trekking mug'), (self.env['product.template'], False))

    def test_tag_is_not_corrected(self):
        # Without the tags among the words the typo correction knows,
        # "trekking" would be corrected to the mug's "trekkies"
        self.assertEqual(self._search('trekking'), (self.boots, False))
        self.assertEqual(self._search('trekkign'), (self.boots, 'trekking'), "A typo in a tag")

    def test_variant_tag(self):
        self.assertEqual(self._search('waterproof'), (self.jacket, False))
        self.jacket.product_variant_ids[0].additional_product_tag_ids = False
        self.assertFalse(self._search('waterproof', allow_fuzzy=False)[0])

    def test_tags_hidden_from_customers(self):
        self.assertFalse(self._search('damaged', allow_fuzzy=False)[0])
        self.damaged.visible_to_customers = True
        self.assertEqual(self._search('damaged'), (self.tent, False))
        self.trekking.visible_to_customers = False
        self.assertFalse(self._search('trekking', allow_fuzzy=False)[0])

    def test_tag_changes(self):
        self.trekking.name = 'Hillwalking'
        self.assertEqual(self._search('hillwalking'), (self.boots, False))
        self.assertFalse(self._search('trekking', allow_fuzzy=False)[0])

        self.boots.product_tag_ids = self.waterproof
        self.assertEqual(self._search('waterproof'), (self.boots | self.jacket, False))

    def test_translated_tag(self):
        self.env['res.lang']._activate_lang('fr_FR')
        self.trekking.update_field_translations('name', {'fr_FR': 'Randonnée'})
        self.assertEqual(self._search('randonnée'), (self.boots, False))
        self.assertEqual(self._search('trekking'), (self.boots, False), "Still in English")

    def test_category_tag(self):
        shelter = self.env['product.tag'].create({'name': 'Shelter'})
        camping = self.env['product.public.category'].create({'name': 'Camping', 'parent_id': self.category.id})
        tents = self.env['product.public.category'].create({'name': 'Tents', 'parent_id': camping.id})
        self.tent.public_categ_ids += tents
        self.jacket.public_categ_ids += camping
        self.assertFalse(self._search('shelter', allow_fuzzy=False)[0])

        camping.product_tag_ids = shelter
        self.assertEqual(self._search('shelter'), (self.jacket | self.tent, False), "Also from a parent category")
        self.assertEqual(self._search('shelter dome'), (self.tent, False), "A word of the tag and one of the name")
        self.assertEqual(self._search('sheltre'), (self.jacket | self.tent, 'shelter'), "A typo in a category tag")

        tents.parent_id = self.category
        self.assertEqual(self._search('shelter'), (self.jacket, False), "No longer in a tagged category")
        self.jacket.public_categ_ids -= camping
        self.assertFalse(self._search('shelter', allow_fuzzy=False)[0])

        self.boots.public_categ_ids += camping
        self.assertEqual(self._search('shelter'), (self.boots, False))
        camping.product_tag_ids = False
        self.assertFalse(self._search('shelter', allow_fuzzy=False)[0])

    def test_category_tag_changes(self):
        shelter = self.env['product.tag'].create({'name': 'Shelter'})
        camping, tents = self.env['product.public.category'].create([
            {'name': 'Camping', 'parent_id': self.category.id, 'product_tag_ids': [Command.set(shelter.ids)]},
            {'name': 'Tents', 'parent_id': self.category.id},
        ])
        self.tent.public_categ_ids += tents
        self.assertFalse(self._search('shelter', allow_fuzzy=False)[0])
        tents.parent_id = camping
        self.assertEqual(self._search('shelter'), (self.tent, False), "Moved under a tagged category")

        shelter.name = 'Bivouac'
        self.assertEqual(self._search('bivouac'), (self.tent, False))
        self.assertFalse(self._search('shelter', allow_fuzzy=False)[0])

        shelter.visible_to_customers = False
        self.assertFalse(self._search('bivouac', allow_fuzzy=False)[0])
        shelter.visible_to_customers = True
        self.assertEqual(self._search('bivouac'), (self.tent, False))

        self.env['res.lang']._activate_lang('fr_FR')
        shelter.update_field_translations('name', {'fr_FR': 'Abri'})
        self.assertEqual(self._search('abri'), (self.tent, False), "Translated category tag")

        camping.unlink()
        self.assertFalse(self._search('bivouac', allow_fuzzy=False)[0], "Category deleted, with its subcategories")

    def test_category_form(self):
        shelter = self.env['product.tag'].create({'name': 'Shelter'})
        with Form(self.env['product.public.category']) as category:
            category.name = 'Camping'
            category.parent_id = self.category
            category.product_tag_ids.add(shelter)
        self.tent.public_categ_ids += category.record
        self.assertEqual(self._search('shelter'), (self.tent, False))

    def test_shop(self):
        page = html.fromstring(self.url_open('/shop', params={'search': 'trekking'}).content)
        names = page.xpath("//h2[contains(@class, 'o_wsale_products_item_title')]/a/span[1]")
        self.assertEqual([name.text_content().strip() for name in names], ['Hiking Boots'])

    def test_header_suggestions(self):
        result = self.make_jsonrpc_request('/website/snippet/autocomplete', {
            'search_type': 'all', 'term': 'waterproof', 'order': 'name asc', 'limit': 5,
            'options': {'displayImage': True, 'displayDescription': True, 'displayExtraLink': True, 'displayDetail': True, 'allowFuzzy': True},
        })
        self.assertEqual([product['name'] for product in result['results']], ['Rain Jacket'])
