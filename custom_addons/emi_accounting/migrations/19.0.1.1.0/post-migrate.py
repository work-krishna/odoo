# -*- coding: utf-8 -*-
"""Tag the EMI receipts booked before account.move.emi_payment_kind existed:
the down payment due and the loans' advances are computed from it."""
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    for app in env['emi.application'].search([]):
        moves = env['account.move'].search([
            ('emi_application_id', '=', app.id), ('emi_payment_kind', '=', False), ('state', '!=', 'draft'),
        ])
        lender = app.finance_company_id.company_id
        for move in moves.filtered('origin_payment_id'):
            if move.company_id == lender:
                move.emi_payment_kind = 'installment'
                continue
            # Marketplace receipt: an installment when it was matched with the
            # entry passing it on to the lender, a down payment otherwise.
            matched = (move.line_ids.matched_debit_ids.debit_move_id
                       | move.line_ids.matched_credit_ids.credit_move_id).move_id
            reclass = matched.filtered(lambda m: m.move_type == 'entry' and not m.origin_payment_id
                                       and m != app.marketplace_move_id and m.emi_application_id == app)
            move.emi_payment_kind = 'installment' if reclass else 'down_payment'
        # Lender entries settling installments the marketplace collected.
        moves.filtered(lambda m: (
            not m.origin_payment_id and m.company_id == lender and m != app.finance_move_id
            and m not in app.schedule_line_ids.due_move_id
            and m.line_ids.filtered(lambda l: l.partner_id == app.company_id.partner_id)
        )).emi_payment_kind = 'installment'
