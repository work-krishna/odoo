# -*- coding: utf-8 -*-
from odoo import fields, models


class EmiPhoneBrand(models.Model):
    """Phone manufacturer (Samsung, Apple, Xiaomi, ...) used to group and
    filter the catalog."""
    _name = 'emi.phone.brand'
    _description = 'Phone Brand'
    _order = 'sequence, name'

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    logo = fields.Image(max_width=256, max_height=256)
    active = fields.Boolean(default=True)
    product_tmpl_ids = fields.One2many('product.template', 'emi_brand_id', string='Phones')

    _name_uniq = models.Constraint('unique(name)', 'This brand already exists.')
