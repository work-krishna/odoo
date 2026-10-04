from odoo import _, api, fields, models, tools
from odoo.exceptions import ValidationError


class ResCompany(models.Model):
    _inherit = 'res.company'

    security_email = fields.Char(
        string="Security Emails From",
        help="Address that sends sign-up codes, invitations, password resets, two-factor codes "
             "and security alerts for this company. Leave empty to use the company email.")
    security_email_formatted = fields.Char(
        string="Formatted Security Email",
        compute='_compute_security_email_formatted', compute_sudo=True)

    @api.depends('security_email', 'name', 'email_formatted')
    def _compute_security_email_formatted(self):
        for company in self:
            if company.security_email:
                company.security_email_formatted = tools.formataddr((company.name, company.security_email))
            else:
                company.security_email_formatted = company.email_formatted

    @api.constrains('security_email')
    def _check_security_email(self):
        for company in self.filtered('security_email'):
            if tools.email_normalize(company.security_email) != company.security_email.strip().lower():
                raise ValidationError(_("%s is not a valid email address.", company.security_email))

    @api.model_create_multi
    def create(self, vals_list):
        companies = super().create(vals_list)
        if any(vals.get('security_email') for vals in vals_list):
            self.env['mail.template']._security_sender_sync_templates()
        return companies

    def write(self, vals):
        res = super().write(vals)
        # Also covers security templates of modules installed after this one.
        if vals.get('security_email'):
            self.env['mail.template']._security_sender_sync_templates()
        return res
