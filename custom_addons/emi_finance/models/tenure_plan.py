# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import UserError


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

    _months_uniq = models.Constraint(
        'unique(months)',
        'A tenure plan for this number of months already exists.',
    )
    _months_positive = models.Constraint(
        'CHECK(months > 0)',
        'Tenure months must be a positive number.',
    )

    @api.depends('months')
    def _compute_name(self):
        for rec in self:
            rec.name = f"{rec.months} months" if rec.months else "New Tenure"

    def _emi_used_records(self):
        """Return the plans that rates or applications already depend on.
        emi_application extends this with plans on submitted applications."""
        rates = self.env['emi.interest.rate'].sudo().with_context(active_test=False).search(
            [('tenure_plan_id', 'in', self.ids)]
        )
        return rates.tenure_plan_id

    def write(self, vals):
        if 'months' in vals:
            used = self._emi_used_records().filtered(lambda p: p.months != vals['months'])
            if used:
                raise UserError(
                    "The length of a tenure plan that interest rates or applications already use "
                    f"cannot change ({', '.join(used.mapped('name'))}). Archive it and create a new plan."
                )
        return super().write(vals)
