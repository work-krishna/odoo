# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import UserError

from odoo.addons.emi_accounting.models.application import BILLING, OFFICER, REVIEWER, _check_collector


class EmiPaymentJournalMixin(models.AbstractModel):
    """Bank or cash journal choice of the EMI payment wizards. The journal
    belongs to the company receiving the money, which is often not one of
    the user's active companies, so a matching journal is pre-selected and
    the wizard explains when there is nothing to choose."""
    _name = 'emi.payment.journal.mixin'
    _description = 'EMI Payment Journal'

    application_id = fields.Many2one('emi.application', required=True, ondelete='cascade')
    currency_id = fields.Many2one(related='application_id.currency_id')
    receiving_company_id = fields.Many2one('res.company', string='Received By', compute='_compute_receiving_company')
    # Not required on the column: stored computes run after the INSERT; action_confirm checks it.
    journal_id = fields.Many2one(
        'account.journal', compute='_compute_journal_id', store=True, readonly=False,
        domain="[('type', 'in', ('bank', 'cash')), ('company_id', '=', receiving_company_id), "
               "'|', ('currency_id', '=', False), ('currency_id', '=', currency_id)]",
        help="Bank or cash journal of the receiving company: where the money comes in (or goes out, for a refund).",
    )
    journal_hint = fields.Char(compute='_compute_journal_hint')

    def _emi_receiving_company(self):
        """Company the money is received by: the marketplace, unless a wizard says otherwise."""
        return self.application_id.sudo().company_id

    def _emi_journals(self):
        self.ensure_one()
        return self.env['account.journal'].sudo().search([
            ('type', 'in', ('bank', 'cash')), ('company_id', '=', self._emi_receiving_company().id),
            '|', ('currency_id', '=', False), ('currency_id', '=', self.currency_id.id),
        ])

    @api.depends('application_id')
    def _compute_receiving_company(self):
        for wiz in self:
            wiz.receiving_company_id = wiz._emi_receiving_company()

    @api.depends('application_id')
    def _compute_journal_id(self):
        for wiz in self:
            wiz.journal_id = wiz._emi_journals()[:1] if wiz.application_id else False

    @api.depends('application_id')
    @api.depends_context('allowed_company_ids')
    def _compute_journal_hint(self):
        for wiz in self:
            company = wiz._emi_receiving_company()
            wiz.journal_hint = False
            if not wiz.application_id:
                continue
            if not wiz._emi_journals():
                wiz.journal_hint = (
                    f"{company.name} has no bank or cash journal in {wiz.currency_id.name} yet. Add one under "
                    f"Accounting > Configuration > Journals (type Bank or Cash) with {company.name} selected "
                    "in the company switcher."
                )
            elif company not in self.env.companies:
                wiz.journal_hint = (
                    f"The journals shown are {company.name}'s: select {company.name} in the company switcher "
                    "(top right) to pick another one."
                )

    def _emi_check_journal(self):
        if not self.journal_id:
            raise UserError(f"Choose the bank or cash journal of {self.receiving_company_id.name} for this payment.")


class EmiInstallmentPayment(models.TransientModel):
    _name = 'emi.installment.payment'
    _inherit = ['emi.payment.journal.mixin']
    _description = 'Register EMI Installment Payment'

    collecting_company_id = fields.Many2one('res.company', compute='_compute_collecting_company')
    # Not required: stored computes run after the INSERT; action_confirm validates it.
    amount = fields.Monetary(compute='_compute_amount', store=True, readonly=False)
    payment_date = fields.Date(required=True, default=fields.Date.context_today)
    memo = fields.Char()

    def _emi_receiving_company(self):
        app = self.application_id.sudo()
        if app.finance_company_id.installment_collection == 'marketplace':
            return app.company_id
        return app.finance_company_id.company_id

    @api.depends('application_id')
    def _compute_collecting_company(self):
        for wiz in self:
            wiz.collecting_company_id = wiz._emi_receiving_company()

    @api.depends('application_id')
    def _compute_amount(self):
        for wiz in self:
            wiz.amount = wiz.application_id.sudo()._emi_amount_due('installment') if wiz.application_id else 0.0

    def action_confirm(self):
        self.ensure_one()
        app = self.application_id.sudo()
        _check_collector(self.env, self.collecting_company_id, (OFFICER, REVIEWER, BILLING))
        self._emi_check_journal()
        app._emi_register_installment_payment(self.amount, self.payment_date, self.journal_id, self.memo)
        return {'type': 'ir.actions.act_window_close'}


class EmiDownPayment(models.TransientModel):
    _name = 'emi.down.payment'
    _inherit = ['emi.payment.journal.mixin']
    _description = 'Register EMI Down Payment'

    company_id = fields.Many2one(related='application_id.company_id')
    amount = fields.Monetary(compute='_compute_amount', store=True, readonly=False)
    payment_date = fields.Date(required=True, default=fields.Date.context_today)

    @api.depends('application_id')
    def _compute_amount(self):
        for wiz in self:
            wiz.amount = wiz.application_id.sudo()._emi_amount_due('down_payment') if wiz.application_id else 0.0

    def action_confirm(self):
        self.ensure_one()
        app = self.application_id.sudo()
        marketplace = app.company_id.sudo()
        _check_collector(self.env, marketplace, (OFFICER, BILLING))
        self._emi_check_journal()
        app._emi_register_down_payment(self.amount, self.payment_date, self.journal_id)
        return {'type': 'ir.actions.act_window_close'}


class EmiDownPaymentRefund(models.TransientModel):
    _name = 'emi.down.payment.refund'
    _inherit = ['emi.payment.journal.mixin']
    _description = 'Refund EMI Down Payment'

    company_id = fields.Many2one(related='application_id.company_id')
    amount = fields.Monetary(compute='_compute_amount', store=True, readonly=False)
    payment_date = fields.Date(required=True, default=fields.Date.context_today)

    @api.depends('application_id')
    def _compute_amount(self):
        for wiz in self:
            wiz.amount = wiz.application_id.sudo()._emi_down_payment_received() if wiz.application_id else 0.0

    def action_confirm(self):
        self.ensure_one()
        app = self.application_id.sudo()
        _check_collector(self.env, app.company_id.sudo(), (OFFICER, BILLING))
        self._emi_check_journal()
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
