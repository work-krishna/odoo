# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import ValidationError


class EmiDownpaymentOption(models.Model):
    """A selectable down payment tier for a specific product.

    A product can offer several options (e.g. 'Minimum 10%', 'Minimum 20%').
    At application time the customer picks one option as their floor, and
    may enter a higher amount voluntarily -- validated against the chosen
    option's minimum in emi_application.
    """
    _name = 'emi.downpayment.option'
    _description = 'EMI Down Payment Option'
    _order = 'product_tmpl_id, sequence'

    product_tmpl_id = fields.Many2one(
        'product.template', string='Product', required=True, ondelete='cascade', index=True,
    )
    name = fields.Char(required=True, help="Label shown to the customer, e.g. '10% Down'.")
    amount_type = fields.Selection(
        [('percent', 'Percentage of Price'), ('fixed', 'Fixed Amount')],
        required=True, default='percent',
    )
    value = fields.Float(
        required=True,
        help="Percentage (0-100) if Amount Type is Percentage, otherwise a fixed currency amount.",
    )
    is_default = fields.Boolean(help="Pre-selected option on the storefront application form.")
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    @api.constrains('amount_type', 'value')
    def _check_value(self):
        for rec in self:
            if rec.value < 0:
                raise ValidationError("Down payment value cannot be negative.")
            if rec.amount_type == 'percent' and rec.value > 100:
                raise ValidationError("A percentage down payment option cannot exceed 100%.")

    def compute_min_amount(self, price):
        """Return the minimum down payment amount in currency for a given price."""
        self.ensure_one()
        if self.amount_type == 'percent':
            return price * (self.value / 100.0)
        return self.value
