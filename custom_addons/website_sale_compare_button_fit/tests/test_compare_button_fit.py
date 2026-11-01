from odoo.fields import Command
from odoo.tests import HttpCase, tagged


@tagged('post_install', '-at_install')
class TestCompareButtonFit(HttpCase):
    browser_size = '800x1000'

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.ref('website_sale.cta_wrapper_large').active = True
        attribute = cls.env['product.attribute'].create({
            'name': 'Storage',
            'value_ids': [Command.create({'name': name}) for name in ('128 GB', '256 GB')],
        })
        cls.product = cls.env['product.template'].create({
            'name': 'Compare Fit Phone',
            'list_price': 100,
            'website_published': True,
            'attribute_line_ids': [Command.create({
                'attribute_id': attribute.id,
                'value_ids': [Command.set(attribute.value_ids.ids)],
            })],
        })

    def test_compare_button_fit(self):
        self.start_tour(self.product.website_url, 'website_sale_compare_button_fit')
