# -*- coding: utf-8 -*-
from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    downpayment_option_ids = fields.One2many(
        'emi.downpayment.option', 'product_tmpl_id',
        string='EMI Down Payment Options',
    )
