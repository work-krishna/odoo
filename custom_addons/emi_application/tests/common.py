# -*- coding: utf-8 -*-
import base64

from odoo.tests.common import TransactionCase, new_test_user

DOC = base64.b64encode(b'test document')


class EmiCommon(TransactionCase):
    """Marketplace company + one finance company, an approved vendor with a
    published phone, and one user per EMI role."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        cls.marketplace = env['res.company']._emi_get_marketplace_company()
        cls.lender_company = env['res.company'].create({'name': 'Lender Co'})
        cls.other_lender_company = env['res.company'].create({'name': 'Other Lender Co'})

        cls.plan_12 = env.ref('emi_finance.tenure_plan_12')
        cls.plan_18 = env.ref('emi_finance.tenure_plan_18')
        cls.finance = env['emi.finance.company'].create({
            'code': 'LND', 'company_id': cls.lender_company.id,
            'tenure_plan_ids': [(6, 0, (cls.plan_12 | cls.plan_18).ids)],
        })
        cls.other_finance = env['emi.finance.company'].create({
            'code': 'OTH', 'company_id': cls.other_lender_company.id,
        })
        cls.rate_12 = env['emi.interest.rate'].create({
            'finance_company_id': cls.finance.id, 'tenure_plan_id': cls.plan_12.id,
            'rate_percent': 0.0, 'calc_method': 'flat', 'date_from': '2020-01-01',
        })
        cls.rate_18 = env['emi.interest.rate'].create({
            'finance_company_id': cls.finance.id, 'tenure_plan_id': cls.plan_18.id,
            'rate_percent': 7.0, 'calc_method': 'reducing', 'date_from': '2020-01-01',
        })

        companies = {'company_id': cls.marketplace.id, 'company_ids': [(6, 0, cls.marketplace.ids)]}
        cls.officer = new_test_user(env, 'emi_officer', groups='emi_finance.group_emi_officer', **companies)
        cls.manager = new_test_user(env, 'emi_manager', groups='emi_finance.group_emi_manager', **companies)
        cls.mp_admin = new_test_user(
            env, 'emi_mp_admin', groups='emi_marketplace.group_emi_marketplace_admin', **companies,
        )
        cls.reviewer = new_test_user(
            env, 'emi_reviewer', groups='emi_finance.group_emi_finance_reviewer',
            company_id=cls.lender_company.id, company_ids=[(6, 0, cls.lender_company.ids)],
        )
        cls.other_reviewer = new_test_user(
            env, 'emi_other_reviewer', groups='emi_finance.group_emi_finance_reviewer',
            company_id=cls.other_lender_company.id, company_ids=[(6, 0, cls.other_lender_company.ids)],
        )
        cls.vendor_user = new_test_user(env, 'emi_vendor_user', groups='base.group_portal')
        cls.customer_user = new_test_user(env, 'emi_customer_user', groups='base.group_portal')
        cls.customer_group = env.ref('emi_application.group_emi_customer_portal')
        cls.customer_user.group_ids = [(4, cls.customer_group.id)]

        vendor_partner = env['res.partner'].create({'name': 'Phone Vendor Pvt Ltd', 'is_company': True})
        cls.vendor_bank = env['res.partner.bank'].create({
            'acc_number': 'NP-VENDOR-001', 'partner_id': vendor_partner.id,
        })
        cls.vendor = env['emi.vendor'].create({
            'partner_id': vendor_partner.id,
            'settlement_bank_account_id': cls.vendor_bank.id,
            'user_ids': [(6, 0, cls.vendor_user.ids)],
        })
        # Uploaded the way the many2many_binary widget does: linked to the record.
        cls.vendor.onboarding_document_ids = [(0, 0, {
            'name': 'registration.pdf', 'datas': DOC, 'res_model': 'emi.vendor', 'res_id': cls.vendor.id,
        })]
        cls.vendor.with_user(cls.mp_admin).action_submit()
        cls.vendor.with_user(cls.mp_admin).action_approve()

        cls.phone_tmpl = env['product.template'].create({
            'name': 'Galaxy Test 128GB', 'list_price': 100000.0, 'vendor_id': cls.vendor.id,
        })
        cls.phone_tmpl.with_user(cls.mp_admin).action_submit_listing()
        cls.phone_tmpl.with_user(cls.mp_admin).action_publish_listing()
        cls.phone = cls.phone_tmpl.product_variant_id

        cls.customer = cls.customer_user.partner_id
        cls.customer.name = 'Ram Bahadur'

    def _kyc_vals(self, **overrides):
        vals = {
            'full_name': 'Ram Bahadur', 'date_of_birth': '1990-01-01', 'phone': '9800000000',
            'citizenship_no': '12-34-56', 'permanent_address': 'Kathmandu', 'occupation': 'salaried',
            'monthly_income': 80000, 'citizenship_front': DOC, 'citizenship_back': DOC,
            'photo': DOC, 'income_proof': DOC,
        }
        vals.update(overrides)
        return vals

    def _draft_application(self, plan=None, **overrides):
        vals = {
            'partner_id': self.customer.id, 'product_id': self.phone.id,
            'finance_company_id': self.finance.id, 'tenure_plan_id': (plan or self.plan_18).id,
            'down_payment_amount': 10000.0, 'delivery_note': 'Deliver to office',
            'kyc_ids': [(0, 0, self._kyc_vals())],
        }
        vals.update(overrides)
        return self.env['emi.application'].with_user(self.officer).create(vals)
