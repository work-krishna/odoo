# -*- coding: utf-8 -*-
from odoo import Command, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError


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

    # States in which staff may still correct KYC data. Any change to
    # identity, income, bank, guarantor or document fields clears the verification.
    _EMI_EDITABLE_STATES = ('draft', 'submitted', 'kyc_review')
    _EMI_UNVERIFY_FIELDS = frozenset({
        'full_name', 'date_of_birth', 'phone', 'citizenship_no', 'citizenship_issue_district',
        'citizenship_issue_date', 'pan_no', 'permanent_address', 'occupation', 'employer_name',
        'monthly_income', 'currency_id', 'bank_name', 'bank_account_no', 'guarantor_name',
        'guarantor_phone', 'guarantor_relation', 'citizenship_front', 'citizenship_back', 'photo',
        'income_proof', 'nid_front', 'nid_back', 'guarantor_citizenship_front', 'guarantor_citizenship_back',
        'guarantor_nid_front', 'guarantor_nid_back', 'guarantor_photo',
    })
    # Needed before the application can be submitted or its KYC verified.
    _EMI_REQUIRED_FIELDS = (
        'full_name', 'date_of_birth', 'phone', 'citizenship_no', 'permanent_address', 'occupation',
        'monthly_income', 'citizenship_front', 'citizenship_back', 'photo', 'income_proof',
        'guarantor_name', 'guarantor_phone', 'guarantor_relation', 'guarantor_citizenship_front',
        'guarantor_citizenship_back', 'guarantor_photo',
    )

    _application_uniq = models.Constraint(
        'unique(application_id)',
        'An application can only have one KYC form.',
    )

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

    # --- Guarantor (required; the national ID card is optional) ---
    guarantor_name = fields.Char()
    guarantor_phone = fields.Char()
    guarantor_relation = fields.Char()
    guarantor_citizenship_front = fields.Binary(string='Guarantor Citizenship Front')
    guarantor_citizenship_front_filename = fields.Char()
    guarantor_citizenship_back = fields.Binary(string='Guarantor Citizenship Back')
    guarantor_citizenship_back_filename = fields.Char()
    guarantor_nid_front = fields.Binary(string='Guarantor NID Front', help="National identity card, if the guarantor has one.")
    guarantor_nid_front_filename = fields.Char()
    guarantor_nid_back = fields.Binary(string='Guarantor NID Back', help="National identity card, if the guarantor has one.")
    guarantor_nid_back_filename = fields.Char()
    guarantor_photo = fields.Binary(string='Guarantor Passport-size Photo')
    guarantor_photo_filename = fields.Char()

    # --- Documents ---
    citizenship_front = fields.Binary(string='Citizenship Front')
    citizenship_front_filename = fields.Char()
    citizenship_back = fields.Binary(string='Citizenship Back')
    citizenship_back_filename = fields.Char()
    photo = fields.Binary(string='Passport-size Photo')
    photo_filename = fields.Char()
    income_proof = fields.Binary(string='Income Proof')
    income_proof_filename = fields.Char()
    nid_front = fields.Binary(string='NID Front', help="National identity card, if the applicant has one.")
    nid_front_filename = fields.Char()
    nid_back = fields.Binary(string='NID Back', help="National identity card, if the applicant has one.")
    nid_back_filename = fields.Char()

    # --- Items configured at runtime under Applications > KYC Requirements ---
    item_ids = fields.One2many('emi.kyc.item', 'kyc_id', string='Additional Items')

    verified = fields.Boolean(
        default=False, tracking=True, readonly=True, copy=False,
        help="Set by the 'Verify KYC' step of the application once an EMI Officer has "
             "checked the identity documents.",
    )
    consent_date = fields.Datetime(
        string='Consent Given On', readonly=True, copy=False,
        help="When the applicant agreed, on the online application, that the marketplace and the "
             "finance company may verify these details.",
    )

    @api.model
    def default_get(self, fields):
        defaults = super().default_get(fields)
        if 'item_ids' in fields and not defaults.get('item_ids'):
            # A new KYC form lists every configured item, ready to fill in.
            requirements = self.env['emi.kyc.requirement'].sudo().search([])
            defaults['item_ids'] = [Command.create({'requirement_id': r.id}) for r in requirements]
        return defaults

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.su:
            if any(vals.get('verified') for vals in vals_list):
                raise AccessError("KYC is verified through the application's 'Verify KYC' step.")
            if any(vals.get('consent_date') for vals in vals_list):
                raise AccessError("The applicant's consent is recorded by the online application.")
            for vals in vals_list:
                # Explicit, so context or user defaults cannot supply them.
                vals.update(verified=False, consent_date=False)
        records = super().create(vals_list)
        # After create, so an application_id from context or user defaults is checked too.
        if not self.env.su and any(rec.application_id.state != 'draft' for rec in records):
            raise UserError("KYC can only be added while the application is a draft.")
        records.sudo()._emi_sync_items()
        return records

    def _emi_sync_items(self):
        """Add an empty item for each active requirement a KYC form does not answer yet."""
        requirements = self.env['emi.kyc.requirement'].sudo().search([])
        self.env['emi.kyc.item'].sudo().create([
            {'kyc_id': kyc.id, 'requirement_id': requirement.id}
            for kyc in self
            for requirement in requirements - kyc.item_ids.requirement_id
        ])

    def write(self, vals):
        if not self.env.su:
            if 'verified' in vals:
                raise AccessError("KYC is verified through the application's 'Verify KYC' step.")
            if 'consent_date' in vals:
                raise AccessError("The applicant's consent is recorded by the online application.")
            if any(rec.application_id.state not in self._EMI_EDITABLE_STATES for rec in self):
                raise UserError("KYC can no longer be changed once the application has left review.")
            if 'application_id' in vals:
                raise UserError("A KYC form cannot be moved to another application.")
            if self._EMI_UNVERIFY_FIELDS & vals.keys():
                vals = dict(vals, verified=False)
        return super().write(vals)

    @api.ondelete(at_uninstall=False)
    def _unlink_except_submitted(self):
        if any(rec.application_id.state != 'draft' for rec in self):
            raise UserError("KYC can only be deleted while the application is a draft.")

    @api.constrains('date_of_birth')
    def _check_age(self):
        for rec in self:
            if not rec.date_of_birth:
                continue
            today = fields.Date.context_today(self)
            age_years = (today - rec.date_of_birth).days / 365.25
            if age_years < 18:
                raise ValidationError("The applicant must be at least 18 years old.")

    def _emi_missing_fields(self):
        """Labels of the required items that are still empty."""
        self.ensure_one()
        kyc = self.with_context(bin_size=True)  # file sizes, not the files themselves
        missing = [self._fields[fname].string for fname in self._EMI_REQUIRED_FIELDS if not kyc[fname]]
        answered = self.sudo().item_ids.filtered('has_value').requirement_id
        required = self.env['emi.kyc.requirement'].sudo().search([('required', '=', True)])
        return missing + (required - answered).mapped('name')

    def is_complete(self):
        """Minimum-completeness check used by emi.application before it can
        be submitted. Kept as a plain method (not a constraint) so a KYC
        record can still be saved as a work-in-progress draft."""
        self.ensure_one()
        return not self._emi_missing_fields()
