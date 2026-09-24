# -*- coding: utf-8 -*-
import json
import logging
from datetime import timedelta

import requests

from odoo import api, fields, models
from odoo.exceptions import UserError

from odoo.addons.l10n_np_ird.tools import bs_calendar

_logger = logging.getLogger(__name__)

CBMS_TIMEOUT = 30
CBMS_MAX_ATTEMPTS = 10
# CBMS response codes (IRD CBMS API specification).
CBMS_CODES = {
    200: "Success",
    100: "API credentials do not match",
    101: "Bill already exists",
    102: "Exception while saving bill details; check the fields and values",
    103: "Unknown exception",
    104: "Invalid model",
    105: "Bill does not exist (sales return)",
}
CBMS_DONE_CODES = (200, 101)  # 101: IRD already holds this bill


class AccountMove(models.Model):
    _inherit = 'account.move'

    l10n_np_date_bs = fields.Char(
        string='Date (BS)', compute='_compute_l10n_np_bs_fields', store=True,
        help="Invoice date in Bikram Sambat.",
    )
    l10n_np_fiscal_year = fields.Char(
        string='Fiscal Year (BS)', compute='_compute_l10n_np_bs_fields', store=True,
        help="Nepali fiscal year of the invoice date, e.g. 2083/84.",
    )
    l10n_np_cbms_state = fields.Selection(
        [('to_send', 'To Send'), ('sent', 'Sent'), ('error', 'Error')],
        string='CBMS Status', copy=False, readonly=True, tracking=True,
    )
    l10n_np_cbms_attempts = fields.Integer(string='CBMS Attempts', copy=False, readonly=True)
    l10n_np_cbms_sent_date = fields.Datetime(string='Sent to CBMS', copy=False, readonly=True)
    l10n_np_cbms_realtime = fields.Boolean(string='Sent in Real Time', copy=False, readonly=True)
    l10n_np_cbms_response = fields.Char(string='Last CBMS Response', copy=False, readonly=True)

    @api.depends('invoice_date', 'date')
    def _compute_l10n_np_bs_fields(self):
        for move in self:
            ref_date = move.invoice_date or move.date
            try:
                move.l10n_np_date_bs = bs_calendar.format_bs(ref_date) if ref_date else False
                move.l10n_np_fiscal_year = (
                    bs_calendar.fiscal_year_label(bs_calendar.fiscal_year_start(ref_date)) if ref_date else False
                )
            except ValueError:
                move.l10n_np_date_bs = move.l10n_np_fiscal_year = False

    # ------------------------------------------------------------------
    # IRD fiscal-year numbering
    # ------------------------------------------------------------------

    def _l10n_np_bs_numbering(self):
        return (
            self.company_id.l10n_np_bs_invoice_numbering
            and self.journal_id.type == 'sale'
            and self.move_type in ('out_invoice', 'out_refund')
        )

    def _get_starting_sequence(self):
        if not self._l10n_np_bs_numbering():
            return super()._get_starting_sequence()
        move_date = self.date or self.invoice_date or fields.Date.context_today(self)
        start_year = bs_calendar.fiscal_year_start(move_date)
        sequence = f"{self.journal_id.code}/{start_year}-{(start_year + 1) % 100:02d}/0000"
        if self.journal_id.refund_sequence and self.move_type == 'out_refund':
            sequence = "R" + sequence
        return sequence

    def _get_sequence_date_range(self, reset):
        if reset == 'year_range' and self._l10n_np_bs_numbering() and self.date:
            start_year = bs_calendar.fiscal_year_start(self.date)
            first, last = bs_calendar.fiscal_year_bounds(start_year)
            # Gregorian bounds for the search, BS years for the number itself.
            return first, last, start_year, start_year + 1
        return super()._get_sequence_date_range(reset)

    def _get_last_sequence(self, relaxed=False, with_prefix=None):
        last = super()._get_last_sequence(relaxed=relaxed, with_prefix=with_prefix)
        if last and self._l10n_np_bs_numbering() and self._deduce_sequence_number_reset(last) != 'year_range':
            # Journal still holds Gregorian-numbered invoices: start the IRD series.
            return None
        return last

    # ------------------------------------------------------------------
    # CBMS
    # ------------------------------------------------------------------

    def _l10n_np_cbms_applicable(self):
        self.ensure_one()
        return self.company_id.l10n_np_cbms_enabled and self.move_type in ('out_invoice', 'out_refund')

    def _post(self, soft=True):
        posted = super()._post(soft=soft)
        to_sync = posted.filtered(lambda m: m._l10n_np_cbms_applicable())
        if to_sync:
            to_sync.write({'l10n_np_cbms_state': 'to_send', 'l10n_np_cbms_attempts': 0})
            cron = self.env.ref('l10n_np_ird.ir_cron_l10n_np_cbms_sync', raise_if_not_found=False)
            if cron:
                cron._trigger()
        return posted

    def button_draft(self):
        synced = self.filtered(lambda m: m.l10n_np_cbms_state == 'sent')
        if synced:
            raise UserError(
                "These invoices are already reported to IRD CBMS and cannot be reset to draft: "
                f"{', '.join(synced.mapped('name'))}. Issue a credit note instead."
            )
        return super().button_draft()

    def _l10n_np_cbms_amounts(self):
        """CBMS amount buckets in company currency, always positive."""
        self.ensure_one()
        vat_group = self._l10n_np_vat13_group()
        export_fp = self.env['account.chart.template'].with_company(self.company_id).ref(
            'fiscal_position_np_export', raise_if_not_found=False,
        )
        is_export = bool(
            (export_fp and self.fiscal_position_id == export_fp)
            or (self.commercial_partner_id.country_id and self.commercial_partner_id.country_id.code != 'NP')
        )
        direction = -1 if self.move_type == 'out_invoice' else 1
        taxable = vat = untaxed_other = 0.0
        for line in self.line_ids:
            amount = line.balance * direction
            if line.display_type == 'product':
                if vat_group and line.tax_ids.filtered(lambda t: t.tax_group_id == vat_group):
                    taxable += amount
                else:
                    untaxed_other += amount
            elif line.display_type == 'tax' and line.tax_line_id.tax_group_id == vat_group:
                vat += amount
        cur = self.company_id.currency_id
        return {
            'total_sales': cur.round(abs(self.amount_total_signed)),
            'taxable_sales_vat': cur.round(taxable),
            'vat': cur.round(vat),
            'excisable_amount': 0.0,
            'excise': 0.0,
            'taxable_sales_hst': 0.0,
            'hst': 0.0,
            'amount_for_esf': 0.0,
            'esf': 0.0,
            'export_sales': cur.round(untaxed_other) if is_export else 0.0,
            'tax_exempted_sales': 0.0 if is_export else cur.round(untaxed_other),
        }

    def _l10n_np_vat13_group(self):
        group = self.env['account.chart.template'].with_company(self.company_id).ref(
            'vat_group_13', raise_if_not_found=False,
        )
        return group or self.env['account.tax.group']

    def _l10n_np_cbms_payload(self, realtime):
        self.ensure_one()
        company = self.company_id.sudo()
        partner = self.commercial_partner_id
        invoice_date = self.invoice_date or self.date
        payload = {
            'username': company.l10n_np_cbms_username or '',
            'password': company.l10n_np_cbms_password or '',
            'seller_pan': company.vat or '',
            'buyer_pan': partner.vat or '',
            'buyer_name': partner.name or '',
            'fiscal_year': bs_calendar.cbms_fiscal_year(bs_calendar.fiscal_year_start(invoice_date)),
            'isrealtime': realtime,
            'datetimeClient': fields.Datetime.now().strftime('%Y-%m-%dT%H:%M:%S'),
            **self._l10n_np_cbms_amounts(),
        }
        if self.move_type == 'out_refund':
            payload.update({
                'ref_invoice_number': self.reversed_entry_id.name or '',
                'credit_note_number': self.name,
                'credit_note_date': bs_calendar.format_bs(invoice_date),
                'reason_for_return': self.ref or 'Sales return',
            })
        else:
            payload.update({
                'invoice_number': self.name,
                'invoice_date': bs_calendar.format_bs(invoice_date),
            })
        return payload

    def _l10n_np_cbms_endpoint(self):
        base = (self.company_id.l10n_np_cbms_url or 'https://cbapi.ird.gov.np').rstrip('/')
        return base + ('/api/billreturn' if self.move_type == 'out_refund' else '/api/bill')

    @staticmethod
    def _l10n_np_cbms_parse(response):
        body = response.text.strip()
        try:
            value = json.loads(body)
        except ValueError:
            value = body.strip('"')
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def _l10n_np_cbms_send(self):
        """Send each move to CBMS once; record the outcome on the move."""
        for move in self:
            if move.state != 'posted' or not move._l10n_np_cbms_applicable():
                continue
            realtime = bool(move.create_date) and fields.Datetime.now() - move.create_date <= timedelta(hours=24)
            payload = move._l10n_np_cbms_payload(realtime)
            try:
                response = requests.post(move._l10n_np_cbms_endpoint(), json=payload, timeout=CBMS_TIMEOUT)
                code = self._l10n_np_cbms_parse(response)
                message = f"{code}: {CBMS_CODES.get(code, 'Unexpected response')}" if code is not None else \
                    f"HTTP {response.status_code}: {response.text[:200]}"
            except requests.RequestException as error:
                code, message = None, f"Connection error: {error}"
            vals = {
                'l10n_np_cbms_attempts': move.l10n_np_cbms_attempts + 1,
                'l10n_np_cbms_response': message,
            }
            if code in CBMS_DONE_CODES:
                vals.update({
                    'l10n_np_cbms_state': 'sent',
                    'l10n_np_cbms_sent_date': fields.Datetime.now(),
                    'l10n_np_cbms_realtime': realtime,
                })
            else:
                vals['l10n_np_cbms_state'] = 'error'
                _logger.warning("CBMS sync failed for %s: %s", move.name, message)
            move.write(vals)
            move.message_post(body=f"IRD CBMS: {message}")

    def action_l10n_np_cbms_send(self):
        self.filtered(lambda m: m.l10n_np_cbms_state in ('to_send', 'error'))._l10n_np_cbms_send()

    @api.model
    def _cron_l10n_np_cbms_sync(self):
        moves = self.search([
            ('l10n_np_cbms_state', 'in', ('to_send', 'error')),
            ('l10n_np_cbms_attempts', '<', CBMS_MAX_ATTEMPTS),
            ('state', '=', 'posted'),
        ], order='date, id', limit=200)
        # No per-move commit needed: a bill re-sent after an interrupted run
        # gets code 101 (already exists), which counts as sent.
        moves._l10n_np_cbms_send()
