from odoo import models


class ResUsers(models.Model):
    _inherit = 'res.users'

    def _notify_security_setting_update(self, subject, content, mail_values=None, **kwargs):
        """ Send "Security Update" alerts from the user's company security email, if it has one. """
        mails = self.env['mail.mail']
        for company, users in self.grouped('company_id').items():
            values = dict(mail_values or {})
            if company.security_email:
                values.setdefault('email_from', company.security_email_formatted)
            mails |= super(ResUsers, users)._notify_security_setting_update(
                subject, content, mail_values=values, **kwargs)
        return mails
