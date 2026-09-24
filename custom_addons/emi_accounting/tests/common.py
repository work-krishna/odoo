# -*- coding: utf-8 -*-
import base64

from odoo.tests.common import new_test_user

from odoo.addons.account.tests.common import AccountTestInvoicingCommon

DOC = base64.b64encode(b'doc')


class EmiAccountingCommon(AccountTestInvoicingCommon):
    """Marketplace + lender companies with EMI accounting set up, EMI users,
    an approved retailer with a published phone and helpers to run a loan."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env(su=True)  # EMI configuration; the flow itself runs as the EMI users
        cls.marketplace = cls.company_data['company']
        env['res.company'].search([('emi_is_marketplace', '=', True)]).emi_is_marketplace = False
        cls.marketplace.emi_is_marketplace = True
        cls.lender_data = cls.setup_other_company(name='Lender Finance Ltd')
        cls.lender = cls.lender_data['company']

        cls.plan_18 = env.ref('emi_finance.tenure_plan_18')
        cls.finance = env['emi.finance.company'].create({'code': 'LFL', 'company_id': cls.lender.id})
        env['emi.interest.rate'].create({
            'finance_company_id': cls.finance.id, 'tenure_plan_id': cls.plan_18.id,
            'rate_percent': 7.0, 'calc_method': 'flat', 'date_from': '2020-01-01',
        })
        (cls.marketplace | cls.lender).action_emi_setup_accounting()

        cls.officer = new_test_user(
            env, 'acc_officer', groups='emi_finance.group_emi_officer',
            company_id=cls.marketplace.id, company_ids=[(6, 0, cls.marketplace.ids)],
        )
        cls.reviewer = new_test_user(
            env, 'acc_reviewer', groups='emi_finance.group_emi_finance_reviewer',
            company_id=cls.lender.id, company_ids=[(6, 0, cls.lender.ids)],
        )
        cls.mp_admin = new_test_user(
            env, 'acc_mp_admin', groups='emi_marketplace.group_emi_marketplace_admin',
            company_id=cls.marketplace.id, company_ids=[(6, 0, cls.marketplace.ids)],
        )

        vendor_partner = env['res.partner'].create({'name': 'Retailer One', 'is_company': True})
        bank = env['res.partner.bank'].create({'acc_number': 'NP-RET-1', 'partner_id': vendor_partner.id})
        cls.vendor = env['emi.vendor'].create({
            'partner_id': vendor_partner.id, 'settlement_bank_account_id': bank.id,
            'commission_type': 'percent', 'commission_value': 5.0,
        })
        cls.vendor.onboarding_document_ids = [(0, 0, {
            'name': 'reg.pdf', 'datas': DOC, 'res_model': 'emi.vendor', 'res_id': cls.vendor.id,
        })]
        cls.vendor.action_submit()
        cls.vendor.action_approve()
        tmpl = env['product.template'].create({'name': 'Phone X', 'list_price': 100000.0, 'vendor_id': cls.vendor.id})
        tmpl.action_submit_listing()
        tmpl.action_publish_listing()
        cls.phone = tmpl.product_variant_id
        cls.customer = env['res.partner'].create({'name': 'Sita Customer'})

    def _approved_application(self):
        app = self.env['emi.application'].with_user(self.officer).create({
            'partner_id': self.customer.id, 'product_id': self.phone.id,
            'finance_company_id': self.finance.id, 'tenure_plan_id': self.plan_18.id,
            'down_payment_amount': 10000.0, 'delivery_note': 'Shop pickup',
            'kyc_ids': [(0, 0, {
                'full_name': 'Sita', 'date_of_birth': '1992-02-02', 'phone': '98', 'citizenship_no': 'C-1',
                'permanent_address': 'Pokhara', 'occupation': 'salaried', 'monthly_income': 60000,
                'citizenship_front': DOC, 'citizenship_back': DOC, 'photo': DOC, 'income_proof': DOC,
            })],
        })
        officer_app = app.with_user(self.officer)
        officer_app.action_submit()
        officer_app.action_start_review()
        officer_app.action_verify_kyc()
        officer_app.action_send_to_finance()
        app.with_user(self.reviewer).action_approve()
        return app

    def _pay_installment(self, app, amount, user=None, journal=None):
        user = user or self.reviewer
        journal = journal or self.lender_data['default_journal_bank']
        wizard = self.env['emi.installment.payment'].with_user(user).create({
            'application_id': app.id, 'amount': amount, 'journal_id': journal.id,
        })
        wizard.action_confirm()

    def _balance(self, account, partner=None):
        domain = [('account_id', '=', account.id), ('parent_state', '=', 'posted')]
        if partner:
            domain.append(('partner_id', '=', partner.id))
        return sum(self.env['account.move.line'].search(domain).mapped('balance'))

