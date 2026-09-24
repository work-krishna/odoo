# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import ValidationError


class EmiFinanceCompany(models.Model):
    """A lending/finance partner that can fund EMI applications.

    Each finance company is backed by its own res.company so that it gets
    its own chart of accounts, journals, sequences and fiscal position,
    while emi.finance.company carries the EMI-specific configuration and
    is what the rest of the EMI models point to.
    """
    _name = 'emi.finance.company'
    _description = 'EMI Finance Company'
    _order = 'name'

    name = fields.Char(related='company_id.name', store=True, readonly=True)
    code = fields.Char(
        required=True,
        help="Short internal code used in application references, e.g. 'NBL' or 'HFC'.",
    )
    company_id = fields.Many2one(
        'res.company',
        string='Odoo Company',
        required=True,
        ondelete='restrict',
        help="The separate Odoo company that owns this finance company's own books.",
    )
    company_partner_id = fields.Many2one(related='company_id.partner_id', string='Company Partner')
    active = fields.Boolean(default=True)

    contact_person = fields.Char()
    phone = fields.Char()
    email = fields.Char()

    min_down_payment_percent = fields.Float(
        string='Default Minimum Down Payment (%)',
        default=0.0,
        help="Fallback minimum down payment percentage when a product does not "
             "define its own down payment options.",
    )

    tenure_plan_ids = fields.Many2many(
        'emi.tenure.plan',
        string='Tenure Plans Offered',
        help="Which tenure plans this finance company is willing to finance. "
             "Leave empty to allow all active tenure plans.",
    )
    interest_rate_ids = fields.One2many(
        'emi.interest.rate', 'finance_company_id', string='Interest Rates',
    )
    interest_rate_count = fields.Integer(compute='_compute_interest_rate_count')

    settlement_bank_account_id = fields.Many2one(
        'res.partner.bank', string='Disbursement Bank Account',
        domain="[('partner_id', '=', company_partner_id)]",
        help="Bank account of the finance company's own Odoo company used for disbursements.",
    )

    _code_uniq = models.Constraint(
        'unique(code)',
        'Finance company code must be unique.',
    )
    _company_uniq = models.Constraint(
        'unique(company_id)',
        'Each Odoo company can only be linked to one finance company record.',
    )
    _min_down_payment_percent_range = models.Constraint(
        'CHECK(min_down_payment_percent >= 0 AND min_down_payment_percent <= 100)',
        'The default minimum down payment must be between 0% and 100%.',
    )

    @api.depends('interest_rate_ids')
    def _compute_interest_rate_count(self):
        for rec in self:
            rec.interest_rate_count = len(rec.interest_rate_ids)

    @api.constrains('company_id')
    def _check_company_not_marketplace(self):
        marketplace = self.env['res.company']._emi_get_marketplace_company()
        for rec in self:
            if rec.company_id == marketplace:
                raise ValidationError(
                    f"{rec.company_id.name} is the EMI marketplace company and cannot also be "
                    "a finance company. Create a separate company for the lender."
                )

    @api.constrains('settlement_bank_account_id', 'company_id')
    def _check_settlement_bank_account(self):
        for rec in self:
            bank = rec.settlement_bank_account_id
            if bank and bank.partner_id.commercial_partner_id != rec.company_id.partner_id.commercial_partner_id:
                raise ValidationError(
                    "The disbursement bank account must belong to the finance company's own Odoo company."
                )

    @api.constrains('tenure_plan_ids')
    def _check_rates_within_offered_tenures(self):
        for rec in self:
            if not rec.tenure_plan_ids:
                continue
            stray = rec.with_context(active_test=False).interest_rate_ids.filtered(
                lambda r: r.tenure_plan_id not in rec.tenure_plan_ids
            )
            if stray:
                raise ValidationError(
                    "These tenure plans still have interest rates for this finance company, so they "
                    f"must stay in 'Tenure Plans Offered': {', '.join(stray.tenure_plan_id.mapped('name'))}."
                )

    def _offers_tenure(self, tenure_plan):
        """True when this finance company finances the given tenure plan."""
        self.ensure_one()
        return not self.tenure_plan_ids or tenure_plan in self.tenure_plan_ids

    def action_view_interest_rates(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Interest Rates',
            'res_model': 'emi.interest.rate',
            'view_mode': 'list,form',
            'domain': [('finance_company_id', '=', self.id)],
            'context': {'default_finance_company_id': self.id},
        }
