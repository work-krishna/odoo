# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import ValidationError


class EmiInterestRate(models.Model):
    """Interest rate configuration per finance company and tenure plan.

    Example policy this supports: 0% for tenures <= 12 months, 7% for
    tenures > 12 months -- expressed as one record per tenure plan rather
    than a single threshold, so each finance company can set its own
    breakpoints and rates independently.
    """
    _name = 'emi.interest.rate'
    _description = 'EMI Interest Rate'
    _order = 'finance_company_id, tenure_plan_id, date_from desc'

    finance_company_id = fields.Many2one(
        'emi.finance.company', required=True, ondelete='cascade', index=True,
    )
    tenure_plan_id = fields.Many2one(
        'emi.tenure.plan', required=True, ondelete='restrict', index=True,
    )
    calc_method = fields.Selection(
        [
            ('flat', 'Flat Rate (on original principal)'),
            ('reducing', 'Reducing Balance (on outstanding principal)'),
        ],
        required=True,
        default='flat',
        help="Determines how emi_accounting builds the amortization schedule "
             "for applications using this rate.",
    )
    rate_percent = fields.Float(
        string='Annual Rate (%)', required=True,
        help="Annual interest rate. Use 0 for interest-free tenures.",
    )
    date_from = fields.Date(required=True, default=fields.Date.context_today)
    date_to = fields.Date(help="Leave empty for an open-ended / currently active rate.")
    active = fields.Boolean(default=True)
    note = fields.Char(help="Internal note, e.g. 'Festival season promo rate'.")

    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        for rec in self:
            if rec.date_to and rec.date_from and rec.date_to < rec.date_from:
                raise ValidationError("The end date cannot be before the start date.")

    @api.constrains('finance_company_id', 'tenure_plan_id', 'date_from', 'date_to', 'active')
    def _check_no_overlap(self):
        for rec in self:
            if not rec.active:
                continue
            domain = [
                ('id', '!=', rec.id),
                ('finance_company_id', '=', rec.finance_company_id.id),
                ('tenure_plan_id', '=', rec.tenure_plan_id.id),
                ('active', '=', True),
            ]
            others = self.search(domain)
            for other in others:
                other_end = other.date_to or fields.Date.from_string('9999-12-31')
                rec_end = rec.date_to or fields.Date.from_string('9999-12-31')
                if rec.date_from <= other_end and other.date_from <= rec_end:
                    raise ValidationError(
                        "Interest rate periods for the same finance company and "
                        "tenure plan cannot overlap. Conflicts with rate dated "
                        f"{other.date_from} to {other.date_to or 'open'}."
                    )

    @api.model
    def get_active_rate(self, finance_company_id, tenure_plan_id, on_date=None):
        """Return the applicable emi.interest.rate record for a given date
        (defaults to today). Used by emi_application when computing an
        application's EMI schedule."""
        on_date = on_date or fields.Date.context_today(self)
        return self.search([
            ('finance_company_id', '=', finance_company_id),
            ('tenure_plan_id', '=', tenure_plan_id),
            ('active', '=', True),
            ('date_from', '<=', on_date),
            '|', ('date_to', '=', False), ('date_to', '>=', on_date),
        ], limit=1)
