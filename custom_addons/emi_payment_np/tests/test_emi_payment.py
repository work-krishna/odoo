# -*- coding: utf-8 -*-
from urllib.parse import parse_qs, urlsplit

from odoo.tests import HttpCase, tagged

from odoo.addons.emi_accounting.tests.common import EmiAccountingCommon
from odoo.addons.payment import utils as payment_utils


@tagged('post_install', '-at_install')
class TestEmiOnlinePayment(EmiAccountingCommon, HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env(su=True)
        method = env.ref('payment.payment_method_unknown')
        redirect_form = env['ir.ui.view'].create({
            'name': 'EMI Test Redirect Form', 'type': 'qweb', 'arch': '<form action="dummy" method="post"/>',
        })
        currency = cls.marketplace.currency_id
        cls.lender_provider = env['payment.provider'].create({
            'name': 'Lender Gateway', 'code': 'none', 'state': 'test', 'is_published': True,
            'company_id': cls.lender.id,
            'journal_id': cls.lender_data['default_journal_bank'].id,
            'payment_method_ids': [(6, 0, method.ids)],
            'redirect_form_view_id': redirect_form.id, 'available_currency_ids': [(6, 0, currency.ids)],
        })
        cls.marketplace_provider = env['payment.provider'].create({
            'name': 'Marketplace Gateway', 'code': 'none', 'state': 'test', 'is_published': True,
            'company_id': cls.marketplace.id,
            'journal_id': cls.company_data['default_journal_bank'].id,
            'payment_method_ids': [(6, 0, method.ids)],
            'redirect_form_view_id': redirect_form.id, 'available_currency_ids': [(6, 0, currency.ids)],
        })
        method.active = True  # archived by default; stands in for eSewa/Khalti/... here
        cls.method = method

    def _online_payment(self, app, kind, provider, amount):
        tx = self.env['payment.transaction'].sudo().create({
            'provider_id': provider.id, 'payment_method_id': self.method.id,
            'amount': amount, 'currency_id': app.currency_id.id, 'partner_id': app.partner_id.id,
            'reference': f'{app.name}-{kind}-{amount}', 'operation': 'online_redirect',
            'emi_application_id': app.id, 'emi_payment_kind': kind,
        })
        tx._set_done()
        tx._post_process()
        return tx

    def test_online_down_payment_and_installment(self):
        app = self._approved_application()
        self.assertEqual(app._emi_amount_due('down_payment'), 10000.0)
        self.assertEqual(app._emi_payment_company('down_payment'), self.marketplace)
        tx = self._online_payment(app, 'down_payment', self.marketplace_provider, 10000.0)
        self.assertTrue(tx.payment_id)
        self.assertEqual(tx.payment_id.company_id, self.marketplace)
        self.assertEqual(app._emi_amount_due('down_payment'), 0.0)

        app.with_user(self.reviewer).action_disburse()
        marketplace_customer_lines = app.marketplace_move_id.line_ids.filtered(lambda l: l.partner_id == self.customer)
        self.assertTrue(marketplace_customer_lines.reconciled)  # online down payment matched

        first = app.schedule_line_ids[0]
        self.assertEqual(app._emi_payment_company('installment'), self.lender)
        self.assertEqual(app._emi_amount_due('installment'), first.amount)
        tx = self._online_payment(app, 'installment', self.lender_provider, first.amount)
        self.assertEqual(first.state, 'paid')
        self.assertEqual(tx.payment_id.company_id, self.lender)
        self.assertEqual(app.state, 'active')
        self.assertEqual(app._emi_amount_due('installment'), app.schedule_line_ids[1].amount)

    def test_marketplace_collection_uses_marketplace_gateway(self):
        self.finance.sudo().installment_collection = 'marketplace'
        app = self._approved_application()
        app.with_user(self.reviewer).action_disburse()
        self.assertEqual(app._emi_payment_company('installment'), self.marketplace)
        first = app.schedule_line_ids[0]
        self._online_payment(app, 'installment', self.marketplace_provider, first.amount)
        self.assertEqual(first.state, 'paid')

    def test_payment_link_token_is_valid(self):
        app = self._approved_application()
        link = app._emi_payment_link('down_payment')
        params = {k: v[0] for k, v in parse_qs(urlsplit(link).query).items()}
        self.assertEqual(params['emi_kind'], 'down_payment')
        self.assertEqual(int(params['company_id']), self.marketplace.id)
        self.assertEqual(params['access_token'], payment_utils.generate_access_token(
            app.partner_id.id, float(params['amount']), app.currency_id.id, env=self.env,
        ))
        self.assertFalse(app._emi_payment_link('installment'))  # not disbursed yet

    def test_portal_pages(self):
        app = self._approved_application()
        app = app.sudo()
        response = self.url_open(f'{app.access_url}?access_token={app._portal_ensure_token()}')
        self.assertEqual(response.status_code, 200)
        self.assertIn(app.name, response.text)
        self.assertIn('Pay Down Payment', response.text)
        # Without a token, an anonymous visitor is sent away.
        response = self.url_open(app.access_url, allow_redirects=False)
        self.assertIn(response.status_code, (302, 303))

    def test_payment_page_uses_server_amount(self):
        app = self._approved_application().sudo()
        link = app._emi_payment_link('down_payment')
        response = self.url_open(link)
        self.assertEqual(response.status_code, 200)
        self.assertIn(f'/emi/transaction/{app.id}/down_payment', response.text)
