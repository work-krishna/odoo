# -*- coding: utf-8 -*-
from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.exceptions import UserError

FREQUENCY_DELTA = {
    'weekly': relativedelta(weeks=1),
    'biweekly': relativedelta(weeks=2),
    'monthly': relativedelta(months=1),
}


class EmiVendorSettlement(models.Model):
    """Pays a retailer what the marketplace collected on their behalf, net
    of the marketplace commission invoices the retailer has not paid yet.

    Posting books: Dr Collections Payable to Retailers (gross) /
    Cr retailer receivable (open commission invoices, up to the gross) /
    Cr retailer payable (net). The net payable is then paid like any vendor
    payable; commission the gross does not cover stays open for the next
    settlement.
    """
    _name = 'emi.vendor.settlement'
    _description = 'EMI Retailer Settlement'
    _inherit = ['mail.thread']
    _order = 'date desc, id desc'

    name = fields.Char(default='New', readonly=True, copy=False)
    vendor_id = fields.Many2one('emi.vendor', required=True, readonly=True, index=True)
    company_id = fields.Many2one(
        'res.company', required=True, readonly=True,
        default=lambda self: self.env['res.company']._emi_get_marketplace_company(),
    )
    currency_id = fields.Many2one(related='company_id.currency_id')
    date = fields.Date(required=True, default=fields.Date.context_today, readonly=True)
    only_collected = fields.Boolean(
        string='Only Fully Collected Sales', default=True, readonly=True,
        help="Include a sale only once the down payment and the finance company's "
             "financing have both been received.",
    )
    state = fields.Selection([('draft', 'Draft'), ('posted', 'Posted'), ('cancel', 'Cancelled')],
                             default='draft', required=True, readonly=True, tracking=True)
    collection_line_ids = fields.Many2many(
        'account.move.line', 'emi_settlement_collection_rel', 'settlement_id', 'line_id',
        string='Collections', readonly=True,
    )
    commission_line_ids = fields.Many2many(
        'account.move.line', 'emi_settlement_commission_rel', 'settlement_id', 'line_id',
        string='Commission Invoices', readonly=True,
    )
    # Plain fields: set when the settlement is drafted/refreshed and frozen
    # at posting (the lines' residuals drop to zero once reconciled).
    gross_amount = fields.Monetary(readonly=True, help="Collections held for the retailer.")
    commission_amount = fields.Monetary(
        readonly=True, help="Unpaid commission invoices netted off, never more than the collections.")
    net_amount = fields.Monetary(readonly=True, help="Amount to pay the retailer.")
    move_id = fields.Many2one('account.move', string='Settlement Entry', readonly=True, copy=False)
    payable_line_id = fields.Many2one('account.move.line', readonly=True, copy=False)
    payment_state = fields.Selection(
        [('not_paid', 'Not Paid'), ('partial', 'Partially Paid'), ('paid', 'Paid')],
        compute='_compute_payment_state', store=True,
    )

    @api.model
    def _lines_vals(self, collections, commissions):
        gross = -sum(collections.mapped('amount_residual'))
        # Never net more than the gross: a negative payout would leave the
        # retailer owing on its payable account, which later runs ignore.
        commission = min(sum(commissions.mapped('amount_residual')), gross)
        return {
            'collection_line_ids': [(6, 0, collections.ids)],
            'commission_line_ids': [(6, 0, commissions.ids)],
            'gross_amount': gross,
            'commission_amount': commission,
            'net_amount': gross - commission,
        }

    @api.depends('state', 'net_amount', 'payable_line_id.amount_residual')
    def _compute_payment_state(self):
        for rec in self:
            line = rec.payable_line_id
            if rec.state != 'posted':
                rec.payment_state = 'not_paid'
            elif not line or not rec.net_amount:
                rec.payment_state = 'paid' if not rec.net_amount else 'not_paid'
            elif rec.currency_id.is_zero(line.amount_residual):
                rec.payment_state = 'paid'
            elif rec.currency_id.compare_amounts(-line.amount_residual, rec.net_amount) < 0:
                rec.payment_state = 'partial'
            else:
                rec.payment_state = 'not_paid'

    @api.model
    def _collect_open_lines(self, vendor, company, only_collected):
        company = company.sudo()
        partner = vendor.partner_id.commercial_partner_id
        MoveLine = self.env['account.move.line'].sudo()
        collections = MoveLine.search([
            ('company_id', '=', company.id), ('partner_id', '=', partner.id),
            ('account_id', '=', company.emi_vendor_clearing_account_id.id),
            ('parent_state', '=', 'posted'), ('reconciled', '=', False), ('balance', '<', 0),
        ])
        if only_collected:
            collections = collections.filtered(lambda l: all(
                sibling.reconciled for sibling in l.move_id.line_ids
                if sibling.account_id.account_type == 'asset_receivable'
            ))
        commissions = MoveLine.search([
            ('company_id', '=', company.id), ('partner_id', '=', partner.id),
            ('account_id.account_type', '=', 'asset_receivable'),
            ('move_id.move_type', '=', 'out_invoice'), ('move_id.emi_application_id', '!=', False),
            ('parent_state', '=', 'posted'), ('reconciled', '=', False),
        ])
        return collections, commissions

    @api.model
    def _create_for_vendor(self, vendor, only_collected=True):
        company = self.env['res.company']._emi_get_marketplace_company()
        company._emi_check_accounting('marketplace')
        collections, commissions = self._collect_open_lines(vendor, company, only_collected)
        if not collections:
            return self.browse()
        return self.sudo().create({
            'vendor_id': vendor.id,
            'company_id': company.id,
            'only_collected': only_collected,
            **self._lines_vals(collections, commissions),
        })

    def action_refresh(self):
        for rec in self.filtered(lambda r: r.state == 'draft'):
            collections, commissions = self._collect_open_lines(rec.vendor_id, rec.company_id, rec.only_collected)
            rec.write(self._lines_vals(collections, commissions))

    def action_post(self):
        for rec in self:
            if rec.state != 'draft':
                raise UserError("Only draft settlements can be posted.")
            rec.action_refresh()
            if not rec.collection_line_ids:
                raise UserError("There is nothing left to settle for this retailer.")
            company = rec.company_id.sudo()
            partner = rec.vendor_id.partner_id.commercial_partner_id
            name = self.env['ir.sequence'].sudo().next_by_code('emi.vendor.settlement') or 'New'
            lines = [(0, 0, {
                'name': f"{name} collections", 'partner_id': partner.id,
                'account_id': company.emi_vendor_clearing_account_id.id, 'debit': rec.gross_amount,
            })]
            if rec.commission_amount:
                lines.append((0, 0, {
                    'name': f"{name} commission invoices", 'partner_id': partner.id,
                    'account_id': partner.with_company(company).property_account_receivable_id.id,
                    'credit': rec.commission_amount,
                }))
            net = rec.net_amount
            if net:
                lines.append((0, 0, {
                    'name': f"{name} payout", 'partner_id': partner.id,
                    'account_id': partner.with_company(company).property_account_payable_id.id,
                    'debit': -net if net < 0 else 0.0, 'credit': net if net > 0 else 0.0,
                }))
            move = self.env['account.move'].sudo().with_company(company).create({
                'move_type': 'entry',
                'journal_id': company.emi_journal_id.id,
                'date': rec.date,
                'ref': f"{name} {rec.vendor_id.name}",
                'line_ids': lines,
            })
            move.action_post()
            clearing = move.line_ids.filtered(lambda l: l.account_id == company.emi_vendor_clearing_account_id)
            (clearing | rec.collection_line_ids).reconcile()
            if rec.commission_line_ids:
                receivable = move.line_ids.filtered(lambda l: l.account_id.account_type == 'asset_receivable')
                (receivable | rec.commission_line_ids).reconcile()
            rec.write({
                'name': name,
                'state': 'posted',
                'move_id': move.id,
                'payable_line_id': move.line_ids.filtered(
                    lambda l: l.account_id.account_type == 'liability_payable').id,
            })

    def action_cancel(self):
        for rec in self:
            if rec.state != 'draft':
                raise UserError("Posted settlements are reversed with Reverse, not cancelled.")
        self.write({'state': 'cancel'})

    def action_reverse(self):
        """Reverse a posted settlement that was not paid out yet: the
        collections and commission invoices it matched are open again for the
        next settlement."""
        self.check_access('write')
        date = fields.Date.context_today(self)
        for rec in self:
            if rec.state != 'posted':
                raise UserError("Only posted settlements can be reversed.")
            if rec.net_amount and rec.payment_state != 'not_paid':
                raise UserError(f"{rec.name} is already paid to the retailer: cancel or unreconcile that "
                                "payment first.")
            rec.move_id.sudo().with_context(emi_reversal=True)._reverse_moves(
                [{'date': date, 'ref': f"Reversal of {rec.name}"}], cancel=True,
            )
            rec.write({'state': 'cancel'})
            rec.message_post(body=f"Reversed by {self.env.user.name}.")

    @api.ondelete(at_uninstall=False)
    def _unlink_except_posted(self):
        if any(rec.state == 'posted' for rec in self):
            raise UserError("Posted settlements cannot be deleted.")

    @api.model
    def _cron_create_settlements(self):
        """Draft a settlement for each approved retailer whose settlement
        period (weekly / bi-weekly / monthly) has elapsed."""
        self = self.sudo()
        today = fields.Date.context_today(self)
        for vendor in self.env['emi.vendor'].search([('state', '=', 'approved')]):
            if self.search_count([('vendor_id', '=', vendor.id), ('state', '=', 'draft')]):
                continue
            last = self.search([('vendor_id', '=', vendor.id), ('state', '=', 'posted')], limit=1)
            if last and last.date + FREQUENCY_DELTA[vendor.settlement_frequency] > today:
                continue
            self._create_for_vendor(vendor)
