# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError


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

    # Fields that define the loan terms. Once an application has been
    # submitted on a rate they are frozen; staff close the period with
    # date_to and add a new rate instead.
    _EMI_LOCKED_FIELDS = frozenset({
        'finance_company_id', 'tenure_plan_id', 'calc_method', 'rate_percent', 'date_from',
    })

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

    _rate_percent_range = models.Constraint(
        'CHECK(rate_percent >= 0 AND rate_percent <= 100)',
        'The annual interest rate must be between 0% and 100%.',
    )

    @api.depends('finance_company_id.code', 'tenure_plan_id.name', 'rate_percent', 'calc_method', 'date_from')
    def _compute_display_name(self):
        methods = dict(self._fields['calc_method']._description_selection(self.env))
        for rec in self:
            method = methods.get(rec.calc_method, '').split(' (')[0]
            rec.display_name = (
                f"{rec.finance_company_id.code or '?'} / {rec.tenure_plan_id.name or '?'} / "
                f"{rec.rate_percent:g}% {method} (from {rec.date_from or '?'})"
            )

    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        for rec in self:
            if rec.date_to and rec.date_from and rec.date_to < rec.date_from:
                raise ValidationError("The end date cannot be before the start date.")

    @api.constrains('finance_company_id', 'tenure_plan_id')
    def _check_tenure_offered(self):
        for rec in self:
            if not rec.finance_company_id._offers_tenure(rec.tenure_plan_id):
                raise ValidationError(
                    f"{rec.finance_company_id.name} does not offer the {rec.tenure_plan_id.name} "
                    "tenure. Add it to the finance company's 'Tenure Plans Offered' first."
                )

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

    def _emi_used_records(self):
        """Return the rates that loan terms depend on. emi_application
        extends this with rates referenced by submitted applications."""
        return self.browse()

    def write(self, vals):
        if self._EMI_LOCKED_FIELDS & vals.keys():
            used = self._emi_used_records()
            if used:
                raise UserError(
                    "These interest rates are already used by submitted applications, so their "
                    "terms cannot change: " + ', '.join(used.mapped('display_name')) + ". "
                    "Set an end date on the current rate and create a new one instead."
                )
        return super().write(vals)

    @api.ondelete(at_uninstall=False)
    def _unlink_except_used(self):
        used = self._emi_used_records()
        if used:
            raise UserError(
                "These interest rates are used by submitted applications and cannot be deleted: "
                + ', '.join(used.mapped('display_name')) + ". Archive them instead."
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
