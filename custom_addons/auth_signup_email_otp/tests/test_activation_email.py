from odoo import Command
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestActivationEmail(TransactionCase):

    def test_activation_email_shows_the_code_link_and_company(self):
        company = self.env['res.company'].create({'name': 'Flagship Test'})
        user = self.env['res.users'].with_context(no_reset_password=True).create({
            'name': 'Sita Sharma',
            'login': 'sita@example.com',
            'email': 'sita@example.com',
            'company_id': company.id,
            'company_ids': [Command.set(company.ids)],
            'group_ids': [Command.set(self.env.ref('base.group_portal').ids)],
        })
        template = self.env.ref('auth_signup_email_otp.mail_template_signup_verification').with_context(
            signup_code='654321', signup_link='https://shop.example/web/signup/activate?token=abc',
            signup_validity=20,
        )
        body = template._render_field('body_html', user.ids)[user.id]

        self.assertIn('654321', body)
        self.assertIn('href="https://shop.example/web/signup/activate?token=abc"', body)
        self.assertIn('expires in 20 minutes', body)
        self.assertIn('Flagship Test', body)
        # the logo is the user's company's, not the main company's
        self.assertIn(f'{user.get_base_url()}/logo.png?company={company.id}', body)
