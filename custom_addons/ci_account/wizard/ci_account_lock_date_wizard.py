# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import AccessError

SOFT_LOCK_DATE_FIELDS = ('fiscalyear_lock_date', 'tax_lock_date', 'sale_lock_date', 'purchase_lock_date')
LOCK_DATE_FIELDS = SOFT_LOCK_DATE_FIELDS + ('hard_lock_date',)
EXCEPTION_DURATIONS = {'5min': timedelta(minutes=5), '15min': timedelta(minutes=15), '1h': timedelta(hours=1),
                       '24h': timedelta(hours=24), 'forever': None}


class CiAccountLockDateWizard(models.TransientModel):
    """Edit the company lock dates. The checks stay those of res.company
    (no hard lock while drafts or unreconciled bank lines exist, the hard lock
    date can never go back, ...)."""
    _name = 'ci.account.lock.date.wizard'
    _description = "Lock Dates"

    company_id = fields.Many2one('res.company', required=True, readonly=True, default=lambda self: self.env.company)
    fiscalyear_lock_date = fields.Date(
        string="Global Lock Date",
        help="No user can create or change entries up to this date, except through a lock date exception.")
    tax_lock_date = fields.Date(
        string="Tax Return Lock Date", help="No entry with taxes can be created or changed up to this date.")
    sale_lock_date = fields.Date(string="Sales Lock Date", help="Locks the sales journals up to this date.")
    purchase_lock_date = fields.Date(string="Purchase Lock Date", help="Locks the purchase journals up to this date.")
    hard_lock_date = fields.Date(
        string="Hard Lock Date",
        help="Irreversible: entries up to this date can never be changed again and the date cannot be moved back.")
    current_hard_lock_date = fields.Date(related='company_id.hard_lock_date', string="Current Hard Lock Date")
    is_loosening = fields.Boolean(compute='_compute_is_loosening')
    loosening_mode = fields.Selection(
        [('exception', "Temporary exception"), ('permanent', "Change the lock date")],
        string="When unlocking", default='exception', required=True,
        help="Moving a lock date back can be limited to some time and to some users: a lock date "
             "exception is recorded instead and the company lock date stays as it is.")
    exception_user = fields.Selection(
        [('me', "Only me"), ('everyone', "Everyone")], string="Exception for", default='me', required=True)
    exception_duration = fields.Selection(
        [('5min', "5 minutes"), ('15min', "15 minutes"), ('1h', "1 hour"), ('24h', "24 hours"),
         ('forever', "Forever")], string="During", default='5min', required=True)
    exception_reason = fields.Char(string="Reason")
    draft_move_count = fields.Integer(compute='_compute_warnings')
    unreconciled_line_count = fields.Integer(compute='_compute_warnings')

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        company = self.env['res.company'].browse(values.get('company_id')) or self.env.company
        for field in LOCK_DATE_FIELDS:
            if field in fields_list:
                values[field] = company[field]
        return values

    @api.depends(*SOFT_LOCK_DATE_FIELDS)
    def _compute_is_loosening(self):
        for wizard in self:
            wizard.is_loosening = bool(wizard._loosened_fields())

    def _loosened_fields(self):
        """Soft lock dates moved back (or removed) compared to the company."""
        self.ensure_one()
        return [field for field in SOFT_LOCK_DATE_FIELDS
                if self.company_id[field] and (not self[field] or self[field] < self.company_id[field])]

    @api.depends('company_id', 'fiscalyear_lock_date', 'hard_lock_date')
    def _compute_warnings(self):
        for wizard in self:
            lock_date = max(filter(None, [wizard.fiscalyear_lock_date, wizard.hard_lock_date]), default=None)
            if not lock_date:
                wizard.draft_move_count = wizard.unreconciled_line_count = 0
                continue
            wizard.draft_move_count = self.env['account.move'].search_count([
                ('company_id', 'child_of', wizard.company_id.id),
                ('state', '=', 'draft'),
                ('date', '<=', lock_date),
            ])
            wizard.unreconciled_line_count = self.env['account.bank.statement.line'].search_count(
                wizard.company_id._get_unreconciled_statement_lines_domain(lock_date))

    def action_save(self):
        self.ensure_one()
        if not self.env.user.has_group('account.group_account_manager'):
            raise AccessError(self.env._("Only accounting administrators can change the lock dates."))
        company = self.company_id
        values = {field: self[field] for field in LOCK_DATE_FIELDS if self[field] != company[field]}
        if self.loosening_mode == 'exception':
            loosened = self._loosened_fields()
            self._create_exceptions(loosened)
            for field in loosened:
                values.pop(field, None)
        if values:
            # res.company is only writable by settings administrators; accounting
            # administrators may still change its lock dates (checked above)
            company.sudo().write(values)
        return {'type': 'ir.actions.act_window_close'}

    def _create_exceptions(self, fields_to_unlock):
        duration = EXCEPTION_DURATIONS[self.exception_duration]
        end = fields.Datetime.now() + duration if duration else False
        self.env['account.lock_exception'].create([{
            'company_id': self.company_id.id,
            'user_id': self.env.user.id if self.exception_user == 'me' else False,
            'lock_date_field': field,
            'lock_date': self[field],
            'end_datetime': end,
            'reason': self.exception_reason,
        } for field in fields_to_unlock])

    def action_open_draft_moves(self):
        self.ensure_one()
        lock_date = max(filter(None, [self.fiscalyear_lock_date, self.hard_lock_date]), default=None)
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._("Draft Entries"),
            'res_model': 'account.move',
            'views': [(False, 'list'), (False, 'form')],
            'domain': [('company_id', 'child_of', self.company_id.id), ('state', '=', 'draft'),
                       ('date', '<=', lock_date)],
        }
