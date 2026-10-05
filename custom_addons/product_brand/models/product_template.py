from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    product_brand_id = fields.Many2one(
        'product.brand', string='Brand', required=True, index=True, ondelete='restrict',
        default=lambda self: self.env['product.brand']._get_no_brand(),
    )
