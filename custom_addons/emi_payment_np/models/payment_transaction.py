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
        of creating a stand-alone customer payment. """
        if not self.emi_application_id:
            return super()._create_payment(**extra_create_values)
        self.ensure_one()
        app = self.emi_application_id.sudo()
        journal = self.provider_id.journal_id
        if not journal:
            raise UserError(_("Set a payment journal on %s to receive EMI payments.", self.provider_id.name))
        if self.emi_payment_kind == 'down_payment':
            payment = app._emi_register_down_payment(self.amount, fields.Date.context_today(self), journal)
        else:
            payment = app._emi_register_installment_payment(
                self.amount, fields.Date.context_today(self), journal, memo=self.reference,
            )
        payment.payment_transaction_id = self
        self.payment_id = payment
        app.message_post(body=_(
            "%(kind)s of %(amount)s received online (%(provider)s, %(ref)s).",
            kind=dict(self._fields['emi_payment_kind']._description_selection(self.env))[self.emi_payment_kind],
            amount=app.currency_id.format(self.amount), provider=self.provider_id.name, ref=self.reference,
        ))
        return payment
