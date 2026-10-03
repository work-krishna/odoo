# -*- coding: utf-8 -*-
from datetime import timedelta

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.exceptions import ValidationError


class CiAccountFiscalYear(models.Model):
    """Explicit fiscal years.

    Companies whose fiscal year does not follow a fixed day/month (the Nepali
    Shrawan to Asar year moves between 16 and 17 July) record their years here;
    ``res.company.compute_fiscalyear_dates`` then uses them everywhere (reports,
    depreciation, lock dates...). Dates not covered by a record fall back on
    the company's fiscal year end day/month.
    """
    _name = 'ci.account.fiscal.year'
    _description = "Fiscal Year"
    _order = 'date_from desc, id desc'

    name = fields.Char(required=True)
    date_from = fields.Date(string="Start Date", required=True)
    date_to = fields.Date(string="End Date", required=True)
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company, index=True)
    is_locked = fields.Boolean(string="Locked", compute='_compute_is_locked',
                               help="Entries of the whole year are protected by the company's global lock date.")

    _check_dates = models.Constraint('CHECK (date_from < date_to)', "The start date must be before the end date.")

    @api.depends('date_to', 'company_id.fiscalyear_lock_date', 'company_id.hard_lock_date')
    def _compute_is_locked(self):
        for fiscal_year in self:
            lock_date = max(filter(None, [fiscal_year.company_id.fiscalyear_lock_date,
                                          fiscal_year.company_id.hard_lock_date]), default=None)
            fiscal_year.is_locked = bool(lock_date and fiscal_year.date_to and lock_date >= fiscal_year.date_to)

    @api.constrains('date_from', 'date_to', 'company_id')
    def _check_overlap(self):
        for fiscal_year in self:
            overlapping = self.search([
                ('id', '!=', fiscal_year.id),
                ('company_id', '=', fiscal_year.company_id.id),
                ('date_from', '<=', fiscal_year.date_to),
                ('date_to', '>=', fiscal_year.date_from),
            ], limit=1)
            if overlapping:
                raise ValidationError(self.env._(
                    "Fiscal year %(name)s overlaps %(other)s.", name=fiscal_year.name, other=overlapping.name))

    def action_create_next(self):
        """Create the fiscal year following the latest one of each company."""
        companies = self.company_id or self.env.company
        created = self.browse()
        for company in companies:
            last = self.search([('company_id', '=', company.id)], order='date_to desc', limit=1)
            vals = self._ci_next_fiscal_year_vals(company, last)
            created |= self.create({**vals, 'company_id': company.id})
        return created

    @api.model
    def _ci_next_fiscal_year_vals(self, company, last):
        """Name and dates of the year after ``last`` (or of the current year)."""
        reference = last.date_to + timedelta(days=1) if last else fields.Date.context_today(self)
        nepali = company._ci_nepali_fiscal_year(reference)
        if nepali:
            date_from, date_to, name = nepali
            return {'name': name, 'date_from': date_from, 'date_to': date_to}
        if last:
            date_from = reference
            date_to = date_from + relativedelta(years=1) - timedelta(days=1)
        else:
            bounds = company.compute_fiscalyear_dates(reference)
            date_from, date_to = bounds['date_from'], bounds['date_to']
        return {'name': company._ci_fiscal_year_name(date_from, date_to), 'date_from': date_from, 'date_to': date_to}


class ResCompany(models.Model):
    _inherit = 'res.company'

    ci_fiscal_year_ids = fields.One2many('ci.account.fiscal.year', 'company_id', string="Fiscal Years")

    def compute_fiscalyear_dates(self, current_date):
        """Use the fiscal year record containing ``current_date``. Without one,
        the day/month rule applies, cut so that it does not overlap a record."""
        self.ensure_one()
        current_date = fields.Date.to_date(current_date)
        FiscalYear = self.env['ci.account.fiscal.year'].sudo()
        fiscal_year = FiscalYear.search([
            ('company_id', '=', self.id),
            ('date_from', '<=', current_date),
            ('date_to', '>=', current_date),
        ], limit=1)
        if fiscal_year:
            return {'date_from': fiscal_year.date_from, 'date_to': fiscal_year.date_to}
        nepali = self._ci_nepali_fiscal_year(current_date)
        if nepali:
            result = {'date_from': nepali[0], 'date_to': nepali[1]}
        else:
            result = super().compute_fiscalyear_dates(current_date)
        previous = FiscalYear.search([
            ('company_id', '=', self.id),
            ('date_to', '<', current_date),
            ('date_to', '>=', result['date_from']),
        ], order='date_to desc', limit=1)
        if previous:
            result['date_from'] = previous.date_to + timedelta(days=1)
        following = FiscalYear.search([
            ('company_id', '=', self.id),
            ('date_from', '>', current_date),
            ('date_from', '<=', result['date_to']),
        ], order='date_from asc', limit=1)
        if following:
            result['date_to'] = following.date_from - timedelta(days=1)
        return result

    def _ci_nepali_fiscal_year(self, current_date):
        """``(date_from, date_to, label)`` of the Nepali fiscal year (1 Shrawan to
        the end of Asar) containing ``current_date``, for Nepali companies when
        l10n_np_ird (which provides the Bikram Sambat calendar) is installed."""
        self.ensure_one()
        if 'l10n_np_bs_invoice_numbering' not in self._fields or self.account_fiscal_country_id.code != 'NP':
            return None
        from odoo.addons.l10n_np_ird.tools import bs_calendar  # noqa: PLC0415 - optional localization
        try:
            start_year = bs_calendar.fiscal_year_start(current_date)
            date_from, date_to = bs_calendar.fiscal_year_bounds(start_year)
        except (ValueError, KeyError, IndexError):  # outside the supported Bikram Sambat range
            return None
        return date_from, date_to, bs_calendar.fiscal_year_label(start_year)

    def _ci_fiscal_year_name(self, date_from, date_to):
        """Name of the fiscal year from ``date_from`` to ``date_to``."""
        self.ensure_one()
        fiscal_year = self.env['ci.account.fiscal.year'].sudo().search([
            ('company_id', '=', self.id), ('date_from', '=', date_from), ('date_to', '=', date_to)], limit=1)
        if fiscal_year:
            return fiscal_year.name
        nepali = self._ci_nepali_fiscal_year(date_from)
        if nepali and (nepali[0], nepali[1]) == (date_from, date_to):
            return nepali[2]
        if date_from.year == date_to.year:
            return str(date_to.year)
        return f"{date_from.year}-{date_to.year}"
