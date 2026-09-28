from odoo import models


class MailTemplate(models.Model):
    _inherit = 'mail.template'

    def send_mail(self, res_id, force_send=False, raise_exception=False, email_values=None,
                  email_layout_xmlid=False):
        # auth_signup welcomes every new account right away; a website sign-up is
        # welcomed once it is activated (see res.users._signup_mark_verified).
        if (self.model == 'res.users'
                and self == self.env.ref('auth_signup.mail_template_user_signup_account_created', False)
                and not self.env['res.users'].sudo().browse(res_id).signup_email_verified):
            return False
        return super().send_mail(res_id, force_send=force_send, raise_exception=raise_exception,
                                 email_values=email_values, email_layout_xmlid=email_layout_xmlid)
