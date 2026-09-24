# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError

OFFICER = 'emi_finance.group_emi_officer'
REVIEWER = 'emi_finance.group_emi_finance_reviewer'
BILLING = 'account.group_account_invoice'


def _check_collector(env, company, groups):
    """Only staff of the collecting company with an EMI or billing role."""
    if env.su:
        return
    if not any(env.user.has_group(g) for g in groups):
        raise AccessError("You are not allowed to register EMI payments.")
    if company not in env.user.company_ids:
        raise AccessError(f"Payments for this loan are collected by {company.name}, which you do not work for.")


class EmiInstallmentPayment(models.TransientModel):
    _name = 'emi.installment.payment'
    _description = 'Register EMI Installment Payment'

    application_id = fields.Many2one('emi.application', required=True, ondelete='cascade')
    collecting_company_id = fields.Many2one('res.company', compute='_compute_collecting_company')
    currency_id = fields.Many2one(related='application_id.currency_id')
    # Not required: stored computes run after the INSERT; action_confirm validates it.
    amount = fields.Monetary(compute='_compute_amount', store=True, readonly=False)
    payment_date = fields.Date(required=True, default=fields.Date.context_today)
    journal_id = fields.Many2one(
        'account.journal', required=True,
        domain="[('type', 'in', ('bank', 'cash')), ('company_id', '=', collecting_company_id)]",
    )
    memo = fields.Char()

    @api.depends('application_id')
    def _compute_collecting_company(self):
        for wiz in self:
            app = wiz.application_id.sudo()
            if app.finance_company_id.installment_collection == 'marketplace':
                wiz.collecting_company_id = app.company_id
            else:
                wiz.collecting_company_id = app.finance_company_id.company_id

    @api.depends('application_id')
    def _compute_amount(self):
        for wiz in self:
            open_lines = wiz.application_id.sudo().schedule_line_ids.filtered(lambda l: l.state != 'paid')
            wiz.amount = open_lines[:1].amount_residual

    def action_confirm(self):
        self.ensure_one()
        app = self.application_id.sudo()
        _check_collector(self.env, self.collecting_company_id, (OFFICER, REVIEWER, BILLING))
        app._emi_register_installment_payment(self.amount, self.payment_date, self.journal_id, self.memo)
        return {'type': 'ir.actions.act_window_close'}


class EmiDownPayment(models.TransientModel):
    _name = 'emi.down.payment'
    _description = 'Register EMI Down Payment'

    application_id = fields.Many2one('emi.application', required=True, ondelete='cascade')
    company_id = fields.Many2one(related='application_id.company_id')
    currency_id = fields.Many2one(related='application_id.currency_id')
    amount = fields.Monetary(compute='_compute_amount', store=True, readonly=False)
    payment_date = fields.Date(required=True, default=fields.Date.context_today)
    journal_id = fields.Many2one(
        'account.journal', required=True,
        domain="[('type', 'in', ('bank', 'cash')), ('company_id', '=', company_id)]",
    )

    @api.depends('application_id')
    def _compute_amount(self):
        for wiz in self:
            wiz.amount = wiz.application_id.down_payment_amount

    def action_confirm(self):
        self.ensure_one()
        app = self.application_id.sudo()
        marketplace = app.company_id.sudo()
        _check_collector(self.env, marketplace, (OFFICER, BILLING))
        app._emi_register_down_payment(self.amount, self.payment_date, self.journal_id)
        return {'type': 'ir.actions.act_window_close'}
