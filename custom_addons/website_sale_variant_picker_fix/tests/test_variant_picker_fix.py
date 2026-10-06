from odoo.fields import Command
from odoo.tests import HttpCase, tagged

from odoo.addons.website_sale.tests.common import WebsiteSaleCommon


@tagged('post_install', '-at_install')
class TestVariantPickerFix(HttpCase, WebsiteSaleCommon):

    def test_single_attribute_grays_out_archived_variant(self):
        color = self.env['product.attribute'].create({
            'name': 'Color', 'display_type': 'color',
            'value_ids': [Command.create({'name': name, 'html_color': html_color}) for name, html_color in (
                ('Black', '#000000'), ('Blue', '#0000FF'), ('Red', '#FF0000'),
            )],
        })
        case = self.env['product.template'].create({
            'name': 'Case', 'list_price': 10, 'website_published': True,
            'attribute_line_ids': [Command.create({'attribute_id': color.id, 'value_ids': [Command.set(color.value_ids.ids)]})],
        })
        case.product_variant_ids.filtered(lambda variant: variant.product_template_attribute_value_ids.name == 'Red').action_archive()
        self.start_tour(case.website_url, 'website_sale_variant_picker_fix_single_attribute')
