from psycopg2 import IntegrityError

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged
from odoo.tools import mute_logger


@tagged('post_install', '-at_install')
class TestProductBrand(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.no_brand = cls.env.ref('product_brand.product_brand_no_brand')
        cls.apple = cls.env['product.brand'].create({'name': 'Apple'})

    def test_new_product_gets_no_brand(self):
        product = self.env['product.template'].create({'name': 'Momo'})
        self.assertEqual(product.product_brand_id, self.no_brand)
        variant = self.env['product.product'].create({'name': 'Chowmein'})
        self.assertEqual(variant.product_brand_id, self.no_brand)

    def test_chosen_brand_is_kept(self):
        product = self.env['product.template'].create({'name': 'iPhone 17 Pro', 'product_brand_id': self.apple.id})
        self.assertEqual(product.product_brand_id, self.apple)
        self.assertEqual(self.apple.product_count, 1)
        self.assertEqual(product.copy().product_brand_id, self.apple)

    def test_brand_is_required(self):
        product = self.env['product.template'].create({'name': 'iPhone 17 Pro'})
        with self.assertRaises(IntegrityError), mute_logger('odoo.sql_db'):
            product.product_brand_id = False
            product.flush_recordset()

    def test_every_product_has_a_brand(self):
        """ Including the products that existed when the module was installed, enforced by the database """
        self.assertFalse(self.env['product.template'].with_context(active_test=False).search_count(
            [('product_brand_id', '=', False)],
        ))
        self.env.cr.execute("""
            SELECT is_nullable FROM information_schema.columns
             WHERE table_name = 'product_template' AND column_name = 'product_brand_id'
        """)
        self.assertEqual(self.env.cr.fetchone()[0], 'NO')

    def test_no_brand_stays_available(self):
        with self.assertRaises(UserError):
            self.no_brand.action_archive()
        with self.assertRaises(UserError):
            self.no_brand.unlink()
        self.no_brand.name = 'Generic'
        self.assertEqual(self.env['product.template'].create({'name': 'Momo'}).product_brand_id, self.no_brand)

    def test_brand_in_use_cannot_be_deleted(self):
        self.env['product.template'].create({'name': 'iPhone 17 Pro', 'product_brand_id': self.apple.id})
        with self.assertRaises(IntegrityError), mute_logger('odoo.sql_db'):
            self.apple.unlink()
        unused = self.env['product.brand'].create({'name': 'Nokia'})
        unused.unlink()
        self.assertFalse(unused.exists())

    def test_brand_names_are_unique(self):
        self.assertEqual(self.apple.copy().name, 'Apple (copy)')
        with self.assertRaises(IntegrityError), mute_logger('odoo.sql_db'):
            self.env['product.brand'].create({'name': 'Apple'})
