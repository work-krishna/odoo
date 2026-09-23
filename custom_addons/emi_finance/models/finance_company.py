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
    )

    _sql_constraints = [
        ('code_uniq', 'unique(code)', 'Finance company code must be unique.'),
        ('company_uniq', 'unique(company_id)',
         'Each Odoo company can only be linked to one finance company record.'),
    ]

    @api.depends('interest_rate_ids')
    def _compute_interest_rate_count(self):
        for rec in self:
            rec.interest_rate_count = len(rec.interest_rate_ids)

    @api.constrains('company_id')
    def _check_company_not_main(self):
        # Placeholder guard: prevent accidentally linking the primary
        # marketplace company as a finance company. Adjust the comparison
        # once the marketplace company is identified via a config parameter.
        for rec in self:
            if not rec.company_id:
                raise ValidationError("A finance company must be linked to an Odoo company.")

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
