from odoo import api, models

# Account-security emails. Templates of modules that are not installed are skipped.
SECURITY_TEMPLATES = (
    'auth_signup.set_password_email',
    'auth_signup.portal_set_password_email',
    'auth_signup.mail_template_user_signup_account_created',
    'auth_signup_email_otp.mail_template_signup_verification',
    'auth_totp_mail.mail_template_totp_invite',
    'auth_totp_mail.mail_template_totp_mail_code',
    'i8_otp_login.otp_email_template_otp_login',
)
COMPANY_FROM = '{{ (object.company_id.email_formatted or user.email_formatted) }}'
SECURITY_FROM = '{{ (object.company_id.security_email_formatted or user.email_formatted) }}'


class MailTemplate(models.Model):
    _inherit = 'mail.template'

    @api.model
    def _security_sender_sync_templates(self, enable=True):
        """ Point the security templates' sender at the company's security email (or back to
        the company email when ``enable`` is False). A sender that was customised is left alone. """
        old, new = (COMPANY_FROM, SECURITY_FROM) if enable else (SECURITY_FROM, COMPANY_FROM)
        for xmlid in SECURITY_TEMPLATES:
            template = self.env.ref(xmlid, raise_if_not_found=False)
            if template and template.email_from == old:
                template.sudo().email_from = new
