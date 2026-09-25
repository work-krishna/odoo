# -*- coding: utf-8 -*-
from odoo import _, fields, models
from odoo.exceptions import UserError

from odoo.addons.payment.logging import get_payment_logger

_logger = get_payment_logger(__name__)


class PaymentTransaction(models.Model):
    _inherit = 'payment.transaction'

    emi_application_id = fields.Many2one('emi.application', string='EMI Application', readonly=True, index=True)
    emi_payment_kind = fields.Selection(
        [('down_payment', 'Down Payment'), ('installment', 'Installment')], readonly=True,
    )

    def _create_payment(self, **extra_create_values):
        """ Override of `account_payment` to book EMI payments against the loan
        (schedule reconciliation, collection by marketplace or lender) instead
        of creating a stand-alone customer payment.

        The gateway already holds the money, so the receipt is always booked:
        the application takes what is due on it and anything it cannot take
        (the loan changed since the payment started) is booked as an
        unallocated customer payment in the collecting company, for staff to
        allocate or refund. """
        if not self.emi_application_id:
            return super()._create_payment(**extra_create_values)
        self.ensure_one()
        app = self.emi_application_id.sudo()
        journal = self.provider_id.journal_id
        if not journal:
            raise UserError(_("Set a payment journal on %s to receive EMI payments.", self.provider_id.name))
        date = fields.Date.context_today(self)
        app._emi_lock()
        if self.emi_payment_kind == 'down_payment':
            due = app._emi_amount_due('down_payment')
        else:
            due = app.amount_outstanding if app.state in ('disbursed', 'active') else 0.0
        amount = min(self.amount, max(due, 0.0))
        payment, problem = self.env['account.payment'], None
        if app.currency_id.compare_amounts(amount, 0.0) <= 0:
            problem = _("nothing is due on it any more")
        else:
            try:
                with self.env.cr.savepoint():
                    if self.emi_payment_kind == 'down_payment':
                        payment = app._emi_register_down_payment(amount, date, journal)
                    else:
                        payment = app._emi_register_installment_payment(amount, date, journal, memo=self.reference)
            except UserError as error:
                payment, problem = self.env['account.payment'], error.args[0]
        if payment:
            payment.payment_transaction_id = self

        unallocated = self.env['account.payment']
        remainder = app.currency_id.round(self.amount - (payment.amount if payment else 0.0))
        if app.currency_id.compare_amounts(remainder, 0.0) > 0:
            method_lines = journal.inbound_payment_method_line_ids
            unallocated = super()._create_payment(**{
                **extra_create_values, 'amount': remainder, 'memo': f"{self.reference} (unallocated)",
                'payment_method_line_id': (
                    method_lines.filtered(lambda l: l.payment_provider_id == self.provider_id) or method_lines
                )[:1].id,
            })
            unallocated.move_id.write({'emi_application_id': app.id, 'emi_payment_kind': 'unallocated'})
        self.payment_id = payment or unallocated
        app._emi_invalidate_summary()

        kind = dict(self._fields['emi_payment_kind']._description_selection(self.env))[self.emi_payment_kind]
        body = _(
            "%(kind)s of %(amount)s received online (%(provider)s, %(ref)s).",
            kind=kind, amount=app.currency_id.format(self.amount), provider=self.provider_id.name,
            ref=self.reference,
        )
        if unallocated:
            note = _(
                "%(amount)s could not be applied to %(app)s (%(reason)s) and is held as unallocated payment "
                "%(payment)s in %(company)s: allocate it or refund the customer.",
                amount=app.currency_id.format(remainder), app=app.name, reason=problem or _("more than is due"),
                payment=unallocated.name, company=unallocated.company_id.name,
            )
            body = f"{body} {note}"
            app.activity_schedule(
                'mail.mail_activity_data_todo', summary=_("Allocate or refund an online payment"), note=note,
                user_id=app._emi_staff_user(unallocated.company_id).id,
            )
        if not self.is_live:
            warning = _("%s is in test mode: no real money was received. Reverse this receipt unless it is a test.",
                        self.provider_id.name)
            body = f"{body} {warning}"
            app.activity_schedule(
                'mail.mail_activity_data_warning', summary=_("Test-mode payment booked"), note=warning,
                user_id=app._emi_staff_user(self.company_id).id,
            )
        app.message_post(body=body)
        return self.payment_id
