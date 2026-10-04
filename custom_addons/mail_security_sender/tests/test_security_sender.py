from unittest.mock import patch

from odoo import Command
from odoo.addons.mail.models.mail_mail import MailMail
from odoo.addons.mail_security_sender.models.mail_template import COMPANY_FROM, SECURITY_FROM
from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestSecuritySender(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env['res.company'].create({
            'name': 'Flagship Test',
            'email': 'sales@flagship.example',
        })
        cls.user = cls.env['res.users'].with_context(no_reset_password=True).create({
            'name': 'Customer',
            'login': 'customer@example.com',
            'email': 'customer@example.com',
            'company_id': cls.company.id,
            'company_ids': [Command.set(cls.company.ids)],
            'group_ids': [Command.set(cls.env.ref('base.group_portal').ids)],
        })
        cls.invite = cls.env.ref('auth_signup.set_password_email')

    def _render_from(self, template):
        return template._render_field('email_from', self.user.ids)[self.user.id]

    def _security_alert_from(self):
        with patch.object(MailMail, 'send', autospec=True):
            mail = self.user._notify_security_setting_update('Security Update', 'Your password changed')
        return mail.email_from

    def test_without_security_email_the_company_email_is_used(self):
        self.assertEqual(self.invite.email_from, SECURITY_FROM)
        self.assertEqual(self._render_from(self.invite), '"Flagship Test" <sales@flagship.example>')
        self.assertEqual(self._security_alert_from(), '"Flagship Test" <sales@flagship.example>')

    def test_security_email_sends_security_emails(self):
        self.company.security_email = 'support@flagship.example'
        for template in self.env['mail.template'].search([('email_from', '=', SECURITY_FROM)]):
            if template.model == 'res.users':
                self.assertEqual(self._render_from(template), '"Flagship Test" <support@flagship.example>', template.name)
        self.assertEqual(self._security_alert_from(), '"Flagship Test" <support@flagship.example>')

    def test_other_companies_are_not_affected(self):
        self.company.security_email = 'support@flagship.example'
        other = self.env['res.company'].create({'name': 'Other Co', 'email': 'info@other.example'})
        self.user.write({'company_ids': [Command.link(other.id)], 'company_id': other.id})
        self.assertEqual(self._render_from(self.invite), '"Other Co" <info@other.example>')
        self.assertEqual(self._security_alert_from(), '"Other Co" <info@other.example>')

    def test_customised_sender_is_kept(self):
        self.invite.email_from = 'hr@flagship.example'
        self.company.security_email = 'support@flagship.example'  # re-syncs the templates
        self.assertEqual(self.invite.email_from, 'hr@flagship.example')

    def test_uninstall_restores_the_company_sender(self):
        self.env['mail.template']._security_sender_sync_templates(enable=False)
        self.assertEqual(self.invite.email_from, COMPANY_FROM)

    def test_security_email_must_be_a_plain_address(self):
        for value in ('support', 'Support <support@flagship.example>'):
            with self.assertRaises(ValidationError):
                self.company.security_email = value
