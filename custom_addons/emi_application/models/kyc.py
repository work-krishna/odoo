# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import ValidationError


class EmiKyc(models.Model):
    """KYC form attached to an EMI application. Kept as its own model
    (rather than fields directly on emi.application) so it can later be
    reused for re-KYC on renewal/top-up applications, and so document
    access can be secured independently of the application record.
    """
    _name = 'emi.kyc'
    _description = 'EMI KYC Form'
    _inherit = ['mail.thread']
    _rec_name = 'full_name'

    application_id = fields.Many2one(
        'emi.application', required=True, ondelete='cascade', index=True,
    )
    partner_id = fields.Many2one(related='application_id.partner_id', store=True, readonly=True)

    # --- Personal details ---
    full_name = fields.Char(required=True, tracking=True)
    gender = fields.Selection([('male', 'Male'), ('female', 'Female'), ('other', 'Other')])
    date_of_birth = fields.Date(required=True)
    phone = fields.Char(required=True)
    email = fields.Char()

    # --- Identity ---
    citizenship_no = fields.Char(string='Citizenship No.', required=True)
    citizenship_issue_district = fields.Char(string='Issue District')
    citizenship_issue_date = fields.Date(string='Issue Date')
    pan_no = fields.Char(string='PAN No.', help="Permanent Account Number (IRD tax ID), if available.")

    # --- Address ---
    permanent_address = fields.Text(required=True)
    temporary_address = fields.Text()

    # --- Income ---
    occupation = fields.Selection(
        [('salaried', 'Salaried'), ('self_employed', 'Self-Employed'),
         ('business', 'Business Owner'), ('other', 'Other')],
        required=True,
    )
    employer_name = fields.Char()
    monthly_income = fields.Monetary(required=True)
    currency_id = fields.Many2one(
        'res.currency', default=lambda self: self.env.company.currency_id, required=True,
    )

    # --- Bank ---
    bank_name = fields.Char()
    bank_account_no = fields.Char()

    # --- Guarantor (optional, used for higher-tenure / higher-amount financing) ---
    guarantor_name = fields.Char()
    guarantor_phone = fields.Char()
    guarantor_relation = fields.Char()

    # --- Documents ---
    citizenship_front = fields.Binary(string='Citizenship Front')
    citizenship_front_filename = fields.Char()
    citizenship_back = fields.Binary(string='Citizenship Back')
    citizenship_back_filename = fields.Char()
    photo = fields.Binary(string='Passport-size Photo')
    photo_filename = fields.Char()
    income_proof = fields.Binary(string='Income Proof')
    income_proof_filename = fields.Char()

    verified = fields.Boolean(
        default=False, tracking=True,
        help="Marked by an EMI Officer once identity documents have been visually verified.",
    )

    @api.constrains('date_of_birth')
    def _check_age(self):
        for rec in self:
            if not rec.date_of_birth:
                continue
            today = fields.Date.context_today(self)
            age_years = (today - rec.date_of_birth).days / 365.25
            if age_years < 18:
                raise ValidationError("The applicant must be at least 18 years old.")

    def is_complete(self):
        """Minimum-completeness check used by emi.application before it can
        be submitted. Kept as a plain method (not a constraint) so a KYC
        record can still be saved as a work-in-progress draft."""
        self.ensure_one()
        required = [
            self.full_name, self.date_of_birth, self.phone, self.citizenship_no,
            self.permanent_address, self.occupation, self.monthly_income,
            self.citizenship_front, self.citizenship_back, self.photo,
        ]
        return all(required)
