# -*- coding: utf-8 -*-
import hashlib
import json
import logging
from datetime import timedelta

import requests

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools.misc import format_date

from odoo.addons.l10n_np_ird.tools import bs_calendar

_logger = logging.getLogger(__name__)

# Invoices and credit notes form the IRD series; receipts and entries of the
# same journal are numbered in series of their own.
IRD_MOVE_TYPES = ('out_invoice', 'out_refund')
BS_SERIES_PREFIXES = {'out_receipt': 'RCPT/', 'entry': 'MISC/'}

CBMS_TIMEOUT = 10
CBMS_MAX_ATTEMPTS = 10
CBMS_BATCH_SIZE = 50
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
# IRD answered and did not store the bill.
CBMS_REJECTED_CODES = (100, 102, 103, 104, 105)
# Payload keys that do not identify the bill IRD stores.
CBMS_FINGERPRINT_SKIPPED_KEYS = (
    'username', 'password', 'isrealtime', 'datetimeClient', 'buyer_name', 'reason_for_return',
)
# Stands for a bill IRD holds that this database has no record of sending.
CBMS_UNKNOWN_BILL = 'unknown'


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
    l10n_np_cbms_posted_date = fields.Datetime(
        string='Posted On', copy=False, readonly=True,
        help="When the invoice was last posted, i.e. issued; CBMS real-time reporting counts from it.",
    )
    l10n_np_cbms_fingerprints = fields.Text(
        string='CBMS Bill Fingerprints', copy=False, readonly=True,
        help="Digests of the versions of this bill IRD may hold. While there is any, the invoice "
             "cannot be reset, cancelled or renamed.",
    )

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
        """Whether the move's journal is numbered per BS fiscal year."""
        return self.company_id.l10n_np_bs_invoice_numbering and self.journal_id.type == 'sale'

    def _l10n_np_fiscal_year_start(self, ad_date=None):
        """BS fiscal year of ``ad_date`` (default: the accounting date), None outside the supported range."""
        ad_date = ad_date or self.date
        if not ad_date:
            return None
        try:
            start_year = bs_calendar.fiscal_year_start(ad_date)
        except ValueError:
            return None
        return start_year if start_year <= bs_calendar.MAX_FISCAL_YEAR else None

    def _l10n_np_is_bs_name(self, name, any_year=False):
        """Whether ``name`` is numbered in the BS fiscal year of the move's date, e.g. INV/2083-84/0001.

        With ``any_year``, any name with a four-digit (BS) start year qualifies.
        """
        if not name or name == '/' or self._deduce_sequence_number_reset(name) != 'year_range':
            return False
        values = self._get_sequence_format_param(name)[1]
        if any_year:
            return values['year_length'] == 4
        start_year = self._l10n_np_fiscal_year_start()
        return (
            values['year'] == self._truncate_year_to_length(start_year, values['year_length'])
            and values['year_end'] == self._truncate_year_to_length(start_year + 1, values['year_end_length'])
        )

    def _l10n_np_bs_sequence(self):
        """Whether the move takes, or already holds, a number of the BS series of its date.

        Moves numbered before the switch (legacy Gregorian names) keep the core behaviour.
        """
        return (
            self._l10n_np_bs_numbering()
            and self._l10n_np_fiscal_year_start() is not None
            and (not self.name or self.name == '/' or self._l10n_np_is_bs_name(self.name))
        )

    def _get_starting_sequence(self):
        if not self._l10n_np_bs_sequence():
            return super()._get_starting_sequence()
        start_year = self._l10n_np_fiscal_year_start()
        series = BS_SERIES_PREFIXES.get(self.move_type, '')
        sequence = f"{self.journal_id.code}/{series}{start_year}-{(start_year + 1) % 100:02d}/0000"
        if self.journal_id.refund_sequence and self.move_type == 'out_refund':
            sequence = "R" + sequence
        return sequence

    def _get_sequence_date_range(self, reset):
        if reset == 'year_range' and self._l10n_np_bs_sequence():
            start_year = self._l10n_np_fiscal_year_start()
            first, last = bs_calendar.fiscal_year_bounds(start_year)
            # Gregorian bounds for the search, BS years for the number itself.
            return first, last, start_year, start_year + 1
        return super()._get_sequence_date_range(reset)

    def _get_last_sequence_domain(self, relaxed=False):
        where_string, param = super()._get_last_sequence_domain(relaxed)
        if not self._l10n_np_bs_sequence():
            return where_string, param
        if not relaxed:
            # Core deduced the range from the format of a reference name, which may be a
            # legacy one: always search the BS fiscal year, as for a year range.
            param['date_start'], param['date_end'] = bs_calendar.fiscal_year_bounds(self._l10n_np_fiscal_year_start())
            param['anti_regex'] = self._make_regex_non_capturing(self._sequence_monthly_regex.split('(?P<seq>')[0]) + '$'
            if (
                '%(anti_regex)s' not in where_string
                and not self.journal_id.sequence_override_regex
                and not self.env.context.get('no_anti_regex')
            ):
                where_string += " AND sequence_prefix !~ %(anti_regex)s "
        # Core picks the prefix of the last move by id, so interleaved series must be
        # separated in the query, not only by their prefixes.
        if self.move_type in IRD_MOVE_TYPES:
            where_string += " AND move_type IN ('out_invoice', 'out_refund') "
        else:
            where_string += " AND move_type = %(l10n_np_move_type)s "
            param['l10n_np_move_type'] = self.move_type
        return where_string, param

    def _get_last_sequence(self, relaxed=False, with_prefix=None):
        last = super()._get_last_sequence(relaxed=relaxed, with_prefix=with_prefix)
        # Only when choosing the next number: chain checks (with_prefix) keep the core behaviour.
        if (
            last and with_prefix is None and self._l10n_np_bs_sequence()
            and not self._l10n_np_is_bs_name(last, any_year=relaxed)
        ):
            # The journal still holds names of another format or fiscal year: start the BS series.
            return None
        return last

    def _l10n_np_check_fiscal_year(self):
        """The number, the BS fiscal year and the CBMS dates must all come from one fiscal year."""
        self.ensure_one()
        start_year = self._l10n_np_fiscal_year_start()
        invoice_year = self._l10n_np_fiscal_year_start(self.invoice_date) if self.invoice_date else start_year
        if start_year is None or invoice_year is None:
            last_day = bs_calendar.fiscal_year_bounds(bs_calendar.MAX_FISCAL_YEAR)[1]
            raise UserError(
                f"{self.display_name}: Nepali fiscal-year numbering supports dates up to "
                f"{format_date(self.env, last_day)}, the end of fiscal year "
                f"{bs_calendar.fiscal_year_label(bs_calendar.MAX_FISCAL_YEAR)}."
            )
        if invoice_year != start_year:
            raise UserError(
                f"{self.display_name}: its invoice date ({format_date(self.env, self.invoice_date)}) is in fiscal year "
                f"{bs_calendar.fiscal_year_label(invoice_year)} but its accounting date "
                f"({format_date(self.env, self.date)}) is in fiscal year {bs_calendar.fiscal_year_label(start_year)}, "
                "usually because the earlier period is locked. IRD numbers invoices per fiscal year of the invoice "
                "date: use an invoice date in the open fiscal year."
            )

    # ------------------------------------------------------------------
    # CBMS
    # ------------------------------------------------------------------

    def _l10n_np_cbms_applicable(self):
        self.ensure_one()
        return self.company_id.l10n_np_cbms_enabled and self.move_type in ('out_invoice', 'out_refund')

    def _post(self, soft=True):
        bs_numbered = self.filtered(lambda m: m._l10n_np_bs_numbering())
        for move in bs_numbered:
            move._l10n_np_check_fiscal_year()
        posted = super()._post(soft=soft)
        # Posting may have moved the accounting date past a lock date.
        for move in posted & bs_numbered:
            move._l10n_np_check_fiscal_year()
        to_sync = posted.filtered(lambda m: m._l10n_np_cbms_applicable())
        if to_sync:
            to_sync.write({
                'l10n_np_cbms_state': 'to_send',
                'l10n_np_cbms_attempts': 0,
                'l10n_np_cbms_posted_date': fields.Datetime.now(),
            })
            cron = self.env.ref('l10n_np_ird.ir_cron_l10n_np_cbms_sync', raise_if_not_found=False)
            if cron:
                cron._trigger()
        return posted

    def _l10n_np_cbms_may_be_stored(self):
        """Whether IRD holds, or may hold, this bill: then its number and content are final."""
        self.ensure_one()
        return self.l10n_np_cbms_state == 'sent' or bool(self.l10n_np_cbms_fingerprints)

    def button_draft(self):
        synced = self.filtered(lambda m: m._l10n_np_cbms_may_be_stored())
        if synced:
            raise UserError(
                "These invoices are reported to IRD CBMS, or IRD may have received them, and cannot be "
                f"reset to draft or cancelled: {', '.join(synced.mapped('name'))}. Issue a credit note instead."
            )
        res = super().button_draft()
        # IRD never stored them: they leave the CBMS queue until posted again.
        self.filtered('l10n_np_cbms_state').write({'l10n_np_cbms_state': False})
        return res

    def write(self, vals):
        fnames = ['name']
        if self.env.context.get('skip_readonly_check'):
            # Core lets these through on posted moves in this context only.
            fnames += ['partner_id', 'date', 'invoice_date', 'line_ids', 'invoice_line_ids', 'currency_id']
        if any(fname in vals for fname in fnames):
            for move in self:
                changed = [f for f in fnames if f in vals and (f != 'name' or vals[f] != move.name)]
                if changed and move._l10n_np_cbms_may_be_stored():
                    raise UserError(
                        f"{move.name} is reported to IRD CBMS, or IRD may have received it: "
                        f"{', '.join(changed)} cannot be changed. Issue a credit note instead."
                    )
        return super().write(vals)

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
        taxable = vat = untaxed_other = rounding = 0.0
        for line in self.line_ids:
            amount = line.balance * direction
            if line.display_type == 'product':
                if vat_group and line.tax_ids.filtered(lambda t: t.tax_group_id == vat_group):
                    taxable += amount
                else:
                    untaxed_other += amount
            elif line.display_type == 'tax' and line.tax_line_id.tax_group_id == vat_group:
                vat += amount
            elif line.display_type == 'rounding':
                rounding += amount
        # Cash rounding carries no VAT: it goes with the untaxed sales, or with the taxable
        # ones when there are only those, so that the buckets add up to total_sales.
        if untaxed_other or not taxable:
            untaxed_other += rounding
        else:
            taxable += rounding
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

    @staticmethod
    def _l10n_np_cbms_fingerprint(payload):
        """Digest of the bill data IRD stores, to recognise a bill it already holds."""
        bill = {key: value for key, value in payload.items() if key not in CBMS_FINGERPRINT_SKIPPED_KEYS}
        return hashlib.sha256(json.dumps(bill, sort_keys=True).encode()).hexdigest()

    @api.model
    def _l10n_np_cbms_commit(self, processed=0, remaining=None):
        """Commit the CBMS progress (cron progress when run by the cron); return the cron's time left."""
        if not self._can_commit():
            return float('inf')
        return self.env['ir.cron']._commit_progress(processed, remaining=remaining)

    def _l10n_np_cbms_send(self):
        """Send each move to CBMS once; record the outcome on the move."""
        for move in self:
            if move.state != 'posted' or not move._l10n_np_cbms_applicable():
                continue
            issued = move.l10n_np_cbms_posted_date or move.create_date
            realtime = bool(issued) and fields.Datetime.now() - issued <= timedelta(hours=24)
            payload = move._l10n_np_cbms_payload(realtime)
            fingerprint = self._l10n_np_cbms_fingerprint(payload)
            held = set((move.l10n_np_cbms_fingerprints or '').split())
            # Record the attempt before sending: if the process dies once IRD has
            # the bill, the invoice stays locked and the retry recognises it.
            move.write({
                'l10n_np_cbms_attempts': move.l10n_np_cbms_attempts + 1,
                'l10n_np_cbms_fingerprints': '\n'.join(sorted(held | {fingerprint})),
            })
            self._l10n_np_cbms_commit()
            try:
                response = requests.post(move._l10n_np_cbms_endpoint(), json=payload, timeout=CBMS_TIMEOUT)
                code = self._l10n_np_cbms_parse(response)
                message = f"{code}: {CBMS_CODES.get(code, 'Unexpected response')}" if code is not None else \
                    f"HTTP {response.status_code}: {response.text[:200]}"
                rejected = code in CBMS_REJECTED_CODES or (code is None and 400 <= response.status_code < 500)
            except requests.RequestException as error:
                code, message, rejected = None, f"Connection error: {error}", False
            vals = {'l10n_np_cbms_response': message}
            if code == 200 or (code == 101 and held == {fingerprint}):
                vals.update({
                    'l10n_np_cbms_state': 'sent',
                    'l10n_np_cbms_sent_date': fields.Datetime.now(),
                    'l10n_np_cbms_realtime': realtime,
                    'l10n_np_cbms_fingerprints': fingerprint,
                })
            else:
                vals['l10n_np_cbms_state'] = 'error'
                if code == 101:
                    # IRD keeps what it had; this version was not stored.
                    vals['l10n_np_cbms_fingerprints'] = '\n'.join(sorted(held)) or CBMS_UNKNOWN_BILL
                    vals['l10n_np_cbms_response'] = message = (
                        f"{message}, but it may differ from this invoice: check the bill in CBMS "
                        "and correct it with a credit note if needed."
                    )
                elif rejected:
                    vals['l10n_np_cbms_fingerprints'] = False
                # Otherwise (no answer, 5xx, unexpected code) IRD may have stored this version.
                _logger.warning("CBMS sync failed for %s: %s", move.name, message)
            move.write(vals)
            move.message_post(body=f"IRD CBMS: {message}")

    def action_l10n_np_cbms_send(self):
        self.filtered(lambda m: m.l10n_np_cbms_state in ('to_send', 'error'))._l10n_np_cbms_send()

    @api.model
    def _cron_l10n_np_cbms_sync(self):
        domain = [
            ('l10n_np_cbms_state', 'in', ('to_send', 'error')),
            ('l10n_np_cbms_attempts', '<', CBMS_MAX_ATTEMPTS),
            ('state', '=', 'posted'),
            ('move_type', 'in', IRD_MOVE_TYPES),
            ('company_id.l10n_np_cbms_enabled', '=', True),
        ]
        moves = self.search(domain, order='date, id', limit=CBMS_BATCH_SIZE)
        remaining = len(moves) if len(moves) < CBMS_BATCH_SIZE else self.search_count(domain)
        time_left = self._l10n_np_cbms_commit(remaining=remaining)
        # One transaction per bill, so that a slow or unreachable IRD loses no outcome.
        for move in moves:
            if not time_left:
                break
            move._l10n_np_cbms_send()
            time_left = self._l10n_np_cbms_commit(1)
