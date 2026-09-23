# -*- coding: utf-8 -*-
from odoo import api, fields, models


class EmiTenurePlan(models.Model):
    """Master data for EMI tenure options (in months).

    Kept as editable data rather than a hardcoded selection so new tenures
    can be added later without a module upgrade.
    """
    _name = 'emi.tenure.plan'
    _description = 'EMI Tenure Plan'
    _order = 'months'

    name = fields.Char(compute='_compute_name', store=True)
    months = fields.Integer(required=True, help="Tenure length in months, e.g. 12.")
    active = fields.Boolean(default=True)
    sequence = fields.Integer(default=10)

    _sql_constraints = [
        ('months_uniq', 'unique(months)', 'A tenure plan for this number of months already exists.'),
        ('months_positive', 'CHECK(months > 0)', 'Tenure months must be a positive number.'),
    ]

    @api.depends('months')
    def _compute_name(self):
        for rec in self:
            rec.name = f"{rec.months} months" if rec.months else "New Tenure"
