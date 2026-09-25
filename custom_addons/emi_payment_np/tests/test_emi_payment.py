# -*- coding: utf-8 -*-
import json
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
        cls.redirect_form = redirect_form

    def _transaction(self, app, kind, provider, amount):
        return self.env['payment.transaction'].sudo().create({
            'provider_id': provider.id, 'payment_method_id': self.method.id,
            'amount': amount, 'currency_id': app.currency_id.id, 'partner_id': app.partner_id.id,
            'reference': f'{app.name}-{kind}-{amount}', 'operation': 'online_redirect',
            'emi_application_id': app.id, 'emi_payment_kind': kind,
        })

    def _online_payment(self, app, kind, provider, amount):
        tx = self._transaction(app, kind, provider, amount)
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
        self._bill(app, 1)
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
        self._bill(app, 1)
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

    # ------------------------------------------------------------------
    # Receipts the application cannot take any more
    # ------------------------------------------------------------------

    def test_receipt_the_loan_no_longer_needs_is_kept(self):
        app = self._approved_application()
        app.with_user(self.reviewer).action_disburse()
        first = app.schedule_line_ids.sorted('number')[0]
        tx = self._transaction(app, 'installment', self.lender_provider, first.amount)
        self._pay_installment(app, app.amount_outstanding)  # the whole loan, at the counter, meanwhile
        tx._set_done()
        tx._post_process()
        self.assertTrue(tx.is_post_processed)
        payment = tx.payment_id
        self.assertIn(payment.state, ('in_process', 'paid'))
        self.assertEqual(payment.amount, first.amount)
        self.assertEqual(payment.company_id, self.lender)
        self.assertEqual(payment.move_id.emi_payment_kind, 'unallocated')
        self.assertEqual(payment.move_id.emi_application_id, app)
        self.assertIn("Allocate or refund an online payment", app.activity_ids.mapped('summary'))
        self.assertAlmostEqual(app.amount_outstanding, 0.0)

    def test_receipt_after_collection_switch_is_kept(self):
        app = self._approved_application()
        app.with_user(self.reviewer).action_disburse()
        first = self._bill(app, 1)
        tx = self._transaction(app, 'installment', self.lender_provider, first.amount)
        self.finance.sudo().installment_collection = 'marketplace'  # while the customer was paying
        tx._set_done()
        tx._post_process()
        self.assertEqual(tx.payment_id.company_id, self.lender)
        self.assertEqual(tx.payment_id.move_id.emi_payment_kind, 'unallocated')
        self.assertNotEqual(first.state, 'paid')
        self.assertTrue(app.activity_ids.filtered(lambda a: a.summary == "Allocate or refund an online payment"))

    def test_down_payment_after_rejection_is_kept(self):
        app = self._submitted_application()
        app.with_user(self.officer).action_start_review()
        tx = self._transaction(app, 'down_payment', self.marketplace_provider, 10000.0)
        app.with_user(self.officer).action_reject("Documents do not match")
        tx._set_done()
        tx._post_process()
        self.assertEqual(tx.payment_id.company_id, self.marketplace)
        self.assertEqual(tx.payment_id.move_id.emi_payment_kind, 'unallocated')
        self.assertEqual(app.down_payment_received, 0.0)

    def test_down_payment_beyond_what_is_due_is_split(self):
        app = self._approved_application()
        tx = self._transaction(app, 'down_payment', self.marketplace_provider, 10000.0)
        self._pay_down_payment(app, 4000.0)  # at the counter, meanwhile
        tx._set_done()
        tx._post_process()
        payments = self.env['account.payment'].sudo().search([('payment_transaction_id', '=', tx.id)])
        self.assertEqual(sorted(payments.mapped('amount')), [4000.0, 6000.0])
        self.assertEqual(tx.payment_id.amount, 6000.0)
        self.assertEqual(tx.payment_id.move_id.emi_payment_kind, 'down_payment')
        unallocated = payments - tx.payment_id
        self.assertEqual(unallocated.move_id.emi_payment_kind, 'unallocated')
        self.assertEqual(app.down_payment_received, 10000.0)
        self.assertEqual(app._emi_amount_due('down_payment'), 0.0)

    def test_test_mode_receipt_is_flagged(self):
        app = self._approved_application()
        tx = self._online_payment(app, 'down_payment', self.marketplace_provider, 10000.0)
        self.assertFalse(tx.is_live)
        self.assertIn("Test-mode payment booked", app.activity_ids.mapped('summary'))

    # ------------------------------------------------------------------
    # Portal and transaction route
    # ------------------------------------------------------------------

    def test_invoice_page_does_not_hand_out_application_token(self):
        app = self._approved_application().sudo()
        invoice = self.env['account.move'].create({
            'move_type': 'out_invoice', 'partner_id': self.vendor.partner_id.id,
            'invoice_line_ids': [(0, 0, {'name': 'Listing fee', 'quantity': 1, 'price_unit': 100.0})],
        })
        invoice.action_post()
        response = self.url_open(
            f'/my/invoices/{invoice.id}?access_token={invoice._portal_ensure_token()}'
            f'&emi_application_id={app.id}&emi_kind=down_payment'
        )
        self.assertEqual(response.status_code, 200)
        app.invalidate_recordset(['access_token'])
        self.assertFalse(app.access_token)
        self.assertNotIn(f'/emi/transaction/{app.id}', response.text)

    def _emi_transaction(self, app, kind, provider, **params):
        response = self.url_open(f'/emi/transaction/{app.id}/{kind}', data=json.dumps({
            'jsonrpc': '2.0', 'method': 'call', 'id': 1, 'params': {
                'access_token': app._portal_ensure_token(), 'provider_id': provider.id,
                'payment_method_id': self.method.id, 'token_id': None, 'flow': 'redirect',
                'tokenization_requested': False, 'landing_route': app.access_url, 'amount': 1.0,
                **params,
            },
        }), headers={'Content-Type': 'application/json'})
        return response.json()

    def test_transaction_route_only_takes_offered_providers(self):
        app = self._approved_application().sudo()
        env = self.env(su=True)
        live = self.marketplace_provider.copy({'name': 'Marketplace Live', 'state': 'enabled', 'is_published': True})
        unpublished = live.copy({'name': 'Marketplace Hidden', 'state': 'enabled', 'is_published': False})
        disabled = live.copy({'name': 'Marketplace Off'})
        self.assertEqual(disabled.state, 'disabled')
        Transaction = env['payment.transaction']
        for provider in (self.marketplace_provider, unpublished, disabled, self.lender_provider):
            self.assertIn('error', self._emi_transaction(app, 'down_payment', provider), provider.name)
        self.assertIn('error', self._emi_transaction(app, 'down_payment', live, is_validation=True))
        self.assertFalse(Transaction.search([('emi_application_id', '=', app.id)]))

        result = self._emi_transaction(app, 'down_payment', live)
        self.assertNotIn('error', result)
        tx = Transaction.search([('emi_application_id', '=', app.id)])
        self.assertEqual(tx.provider_id, live)
        self.assertEqual(tx.amount, 10000.0)  # the server's amount, not the posted one
