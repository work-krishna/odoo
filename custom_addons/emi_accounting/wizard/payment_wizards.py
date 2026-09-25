# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import UserError

from odoo.addons.emi_accounting.models.application import BILLING, OFFICER, REVIEWER, _check_collector

JOURNAL_DOMAIN = ("[('type', 'in', ('bank', 'cash')), ('company_id', '=', {company}), "
                  "'|', ('currency_id', '=', False), ('currency_id', '=', currency_id)]")


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
        'account.journal', required=True, domain=JOURNAL_DOMAIN.format(company='collecting_company_id'),
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
            wiz.amount = wiz.application_id.sudo()._emi_amount_due('installment') if wiz.application_id else 0.0

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
    journal_id = fields.Many2one('account.journal', required=True, domain=JOURNAL_DOMAIN.format(company='company_id'))

    @api.depends('application_id')
    def _compute_amount(self):
        for wiz in self:
            wiz.amount = wiz.application_id.sudo()._emi_amount_due('down_payment') if wiz.application_id else 0.0

    def action_confirm(self):
        self.ensure_one()
        app = self.application_id.sudo()
        marketplace = app.company_id.sudo()
        _check_collector(self.env, marketplace, (OFFICER, BILLING))
        app._emi_register_down_payment(self.amount, self.payment_date, self.journal_id)
        return {'type': 'ir.actions.act_window_close'}


class EmiDownPaymentRefund(models.TransientModel):
    _name = 'emi.down.payment.refund'
    _description = 'Refund EMI Down Payment'

    application_id = fields.Many2one('emi.application', required=True, ondelete='cascade')
    company_id = fields.Many2one(related='application_id.company_id')
    currency_id = fields.Many2one(related='application_id.currency_id')
    amount = fields.Monetary(compute='_compute_amount', store=True, readonly=False)
    payment_date = fields.Date(required=True, default=fields.Date.context_today)
    journal_id = fields.Many2one('account.journal', required=True, domain=JOURNAL_DOMAIN.format(company='company_id'))

    @api.depends('application_id')
    def _compute_amount(self):
        for wiz in self:
            wiz.amount = wiz.application_id.sudo()._emi_down_payment_received() if wiz.application_id else 0.0

    def action_confirm(self):
        self.ensure_one()
        app = self.application_id.sudo()
        _check_collector(self.env, app.company_id.sudo(), (OFFICER, BILLING))
        app._emi_refund_down_payment(self.amount, self.payment_date, self.journal_id)
        return {'type': 'ir.actions.act_window_close'}


class EmiForeclosure(models.TransientModel):
    _name = 'emi.foreclosure'
    _description = 'EMI Early Settlement'

    application_id = fields.Many2one('emi.application', required=True, ondelete='cascade')
    currency_id = fields.Many2one(related='application_id.currency_id')
    date = fields.Date(required=True, default=fields.Date.context_today, readonly=True)
    principal_amount = fields.Monetary(string='Principal Outstanding', compute='_compute_quote')
    interest_amount = fields.Monetary(string='Interest Accrued', compute='_compute_quote')
    amount = fields.Monetary(string='Payoff', compute='_compute_quote')
    note = fields.Char(compute='_compute_quote')

    @api.depends('application_id', 'date')
    def _compute_quote(self):
        for wiz in self:
            wiz.principal_amount = wiz.interest_amount = wiz.amount = 0.0
            wiz.note = False
            if not wiz.application_id:
                continue
            try:
                quote = wiz.application_id.sudo()._emi_foreclosure_quote(wiz.date)
            except UserError as error:
                wiz.note = str(error)
                continue
            wiz.principal_amount = quote['principal']
            wiz.interest_amount = quote['interest']
            wiz.amount = quote['amount']

    def action_confirm(self):
        self.ensure_one()
        self.application_id.action_emi_foreclose(self.date)
        return {'type': 'ir.actions.act_window_close'}
