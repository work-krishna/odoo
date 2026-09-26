# -*- coding: utf-8 -*-
import math

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tools import format_date


class EmiKycRequirement(models.Model):
    """An extra item the KYC asks for, added at runtime by an EMI Manager
    (e.g. a signed consent form). The backend KYC form and the online
    application show every active requirement; required ones must be
    provided before an application can be submitted or its KYC verified."""
    _name = 'emi.kyc.requirement'
    _description = 'EMI KYC Requirement'
    _order = 'party, sequence, id'

    name = fields.Char(required=True, translate=True, help="Label shown on the KYC form and the online application.")
    party = fields.Selection(
        [('applicant', 'Applicant'), ('guarantor', 'Guarantor')],
        string='Asked Of', required=True, default='applicant',
    )
    value_type = fields.Selection(
        [('file', 'File Upload'), ('text', 'Text'), ('number', 'Number'), ('date', 'Date'), ('checkbox', 'Checkbox')],
        string='Type', required=True, default='file',
        help="A required checkbox has to be ticked, e.g. to confirm a statement.",
    )
    required = fields.Boolean(help="Needed before the application can be submitted or its KYC verified.")
    description = fields.Text(help="Instructions shown under the field, e.g. who has to sign the form.")
    template = fields.Binary(
        string='Blank Form',
        help="For file uploads: a form the customer can download, fill in (and sign) and upload.",
    )
    template_filename = fields.Char()
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    item_ids = fields.One2many('emi.kyc.item', 'requirement_id')

    @api.model_create_multi
    def create(self, vals_list):
        requirements = super().create(vals_list)
        requirements._sync_open_kycs()
        return requirements

    def write(self, vals):
        if {'party', 'value_type'} & vals.keys() and self.sudo().item_ids.filtered('has_value'):
            raise UserError(
                "KYC forms already hold answers for this item, so who it is asked of and its type cannot "
                "change. Archive it and add a new one instead."
            )
        result = super().write(vals)
        if vals.get('active'):
            self._sync_open_kycs()
        return result

    @api.ondelete(at_uninstall=False)
    def _unlink_except_answered(self):
        if self.sudo().item_ids.filtered('has_value'):
            raise UserError("KYC forms already hold answers for this item: archive it instead.")

    def _sync_open_kycs(self):
        """KYC forms still being filled in or reviewed ask for new items right away."""
        Kyc = self.env['emi.kyc'].sudo()
        Kyc.search([('application_id.state', 'in', Kyc._EMI_EDITABLE_STATES)])._emi_sync_items()


class EmiKycItem(models.Model):
    """A KYC form's answer to one configured requirement."""
    _name = 'emi.kyc.item'
    _description = 'EMI KYC Item'
    _order = 'requirement_id, id'

    _EMI_VALUE_FIELDS = frozenset({'value_text', 'value_date', 'value_bool', 'value_file', 'value_filename'})

    _requirement_uniq = models.Constraint(
        'unique(kyc_id, requirement_id)',
        'A KYC form answers each item only once.',
    )

    kyc_id = fields.Many2one('emi.kyc', string='KYC', required=True, ondelete='cascade', index=True)
    requirement_id = fields.Many2one('emi.kyc.requirement', required=True, ondelete='cascade', index=True)
    name = fields.Char(related='requirement_id.name', string='Item')
    party = fields.Selection(related='requirement_id.party', store=True)
    value_type = fields.Selection(related='requirement_id.value_type')
    required = fields.Boolean(related='requirement_id.required')
    description = fields.Text(related='requirement_id.description')
    template = fields.Binary(related='requirement_id.template', string='Blank Form')
    template_filename = fields.Char(related='requirement_id.template_filename')

    value_text = fields.Char(string='Answer')
    value_date = fields.Date(string='Date')
    value_bool = fields.Boolean(string='Confirmed')
    value_file = fields.Binary(string='File')
    value_filename = fields.Char()
    has_value = fields.Boolean(string='Provided', compute='_compute_has_value', store=True)
    value_display = fields.Char(string='Value', compute='_compute_value_display')

    @api.depends('value_type', 'value_text', 'value_date', 'value_bool', 'value_file')
    def _compute_has_value(self):
        for item in self:
            if item.value_type == 'file':
                item.has_value = bool(item.value_file)
            elif item.value_type == 'date':
                item.has_value = bool(item.value_date)
            elif item.value_type == 'checkbox':
                item.has_value = item.value_bool
            else:
                item.has_value = bool((item.value_text or '').strip())

    @api.depends('value_type', 'value_text', 'value_date', 'value_bool', 'value_filename', 'has_value')
    def _compute_value_display(self):
        for item in self:
            if item.value_type == 'file':
                item.value_display = item.value_filename or ('Uploaded' if item.has_value else False)
            elif item.value_type == 'date':
                item.value_display = format_date(self.env, item.value_date) if item.value_date else False
            elif item.value_type == 'checkbox':
                item.value_display = 'Yes' if item.value_bool else 'No'
            else:
                item.value_display = item.value_text

    @api.constrains('value_text', 'requirement_id')
    def _check_number(self):
        for item in self:
            if item.value_type != 'number' or not (item.value_text or '').strip():
                continue
            try:
                number = float(item.value_text.replace(',', ''))
            except ValueError:
                number = math.inf
            if not math.isfinite(number) or abs(number) >= 1e12:
                raise ValidationError(f"{item.name}: enter a number.")

    @api.model_create_multi
    def create(self, vals_list):
        items = super().create(vals_list)
        if not self.env.su:
            items._check_editable()
            items.kyc_id.sudo().filtered('verified').write({'verified': False})
        return items

    def write(self, vals):
        if not self.env.su:
            if vals.keys() - self._EMI_VALUE_FIELDS:
                raise AccessError("Only the answer of a KYC item can be changed.")
            self._check_editable()
        result = super().write(vals)
        if not self.env.su:
            # Like the KYC's own documents: a changed answer needs checking again.
            self.kyc_id.sudo().filtered('verified').write({'verified': False})
        return result

    @api.ondelete(at_uninstall=False)
    def _unlink_except_user(self):
        if not self.env.su:
            raise UserError("KYC items follow the configured requirements: clear the answer instead.")

    def _check_editable(self):
        states = self.env['emi.kyc']._EMI_EDITABLE_STATES
        if any(item.kyc_id.application_id.state not in states for item in self):
            raise UserError("KYC can no longer be changed once the application has left review.")
