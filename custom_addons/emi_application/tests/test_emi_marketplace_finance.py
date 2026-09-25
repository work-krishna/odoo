# -*- coding: utf-8 -*-
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import tagged

from .common import DOC, EmiCommon


@tagged('post_install', '-at_install')
class TestEmiMarketplaceSecurity(EmiCommon):

    def test_vendor_portal_group_synced_from_vendor_users(self):
        group = self.env.ref('emi_marketplace.group_emi_vendor_portal')
        self.assertIn(self.vendor_user, group.user_ids)
        self.vendor.user_ids = [(5, 0, 0)]
        self.assertNotIn(self.vendor_user, group.user_ids)

    def test_vendor_portal_cannot_approve_or_edit_terms(self):
        as_vendor = self.vendor.with_user(self.vendor_user)
        self.assertEqual(as_vendor.name, 'Phone Vendor Pvt Ltd')  # can read own record
        with self.assertRaises(AccessError):
            as_vendor.write({'commission_value': 0.0})
        self.vendor.with_user(self.mp_admin).action_suspend()
        with self.assertRaises(AccessError):
            as_vendor.action_approve()

    def test_listing_moderation_is_admin_only(self):
        tmpl = self.env['product.template'].create({'name': 'Pixel Test', 'vendor_id': self.vendor.id})
        product_manager = self.env['res.users'].create({
            'name': 'Product Manager', 'login': 'emi_prod_mgr',
            'group_ids': [(6, 0, [self.env.ref('base.group_user').id, self.env.ref('product.group_product_manager').id])],
        })
        with self.assertRaises(AccessError):
            tmpl.with_user(product_manager).write({'listing_state': 'published'})
        with self.assertRaises(AccessError):
            self.env['product.template'].with_user(product_manager).create({
                'name': 'Sneaky', 'vendor_id': self.vendor.id, 'listing_state': 'published',
            })
        tmpl.with_user(self.vendor_user).action_submit_listing()
        with self.assertRaises(AccessError):
            tmpl.with_user(self.vendor_user).action_publish_listing()
        with self.assertRaises(AccessError):
            tmpl.with_user(product_manager).action_publish_listing()
        tmpl.with_user(self.mp_admin).action_publish_listing()
        self.assertEqual(tmpl.listing_state, 'published')

    def test_defaults_cannot_publish_new_listing(self):
        product_manager = self.env['res.users'].create({
            'name': 'Product Manager', 'login': 'emi_prod_mgr',
            'group_ids': [(6, 0, [self.env.ref('base.group_user').id, self.env.ref('product.group_product_manager').id])],
        })
        Product = self.env['product.template'].with_user(product_manager)
        published = Product.with_context(default_listing_state='published')
        self.assertEqual(published.create({'name': 'Sneaky', 'vendor_id': self.vendor.id}).listing_state, 'draft')
        self.assertEqual(self.phone_tmpl.with_user(product_manager).with_context(
            default_listing_state='published').copy().listing_state, 'draft')
        self.env['ir.default'].with_user(product_manager).set(
            'product.template', 'listing_state', 'published', user_id=True)
        self.assertEqual(Product.create({'name': 'Sneaky 2', 'vendor_id': self.vendor.id}).listing_state, 'draft')
        # A Marketplace Admin's own defaults still apply.
        admin_listing = self.env['product.template'].with_user(self.mp_admin).with_context(
            default_listing_state='published').create({'name': 'Admin Phone', 'vendor_id': self.vendor.id})
        self.assertEqual(admin_listing.listing_state, 'published')

    def test_listing_price_must_be_real(self):
        for price in (float('nan'), float('inf')):
            with self.assertRaises(ValidationError):
                self.env['product.template'].create({'name': 'Bad Price', 'list_price': price, 'vendor_id': self.vendor.id})
        with self.assertRaises(ValidationError):
            self.phone_tmpl.list_price = 0.0  # published
        tmpl = self.env['product.template'].create({'name': 'Free Phone', 'list_price': 0.0, 'vendor_id': self.vendor.id})
        tmpl.with_user(self.mp_admin).action_submit_listing()
        with self.assertRaises(ValidationError):
            tmpl.with_user(self.mp_admin).action_publish_listing()

    def test_copy_of_published_listing_is_draft(self):
        self.assertEqual(self.phone_tmpl.copy().listing_state, 'draft')

    def test_suspending_vendor_withdraws_listings(self):
        self.vendor.with_user(self.mp_admin).action_suspend()
        self.assertEqual(self.phone_tmpl.listing_state, 'pending_review')
        with self.assertRaises(UserError):
            self.phone_tmpl.with_user(self.mp_admin).action_publish_listing()
        self.vendor.with_user(self.mp_admin).action_approve()
        self.phone_tmpl.with_user(self.mp_admin).action_publish_listing()

    def test_publish_requires_approved_vendor(self):
        partner = self.env['res.partner'].create({'name': 'New Vendor'})
        vendor = self.env['emi.vendor'].create({'partner_id': partner.id})
        tmpl = self.env['product.template'].create({'name': 'Unapproved Phone', 'vendor_id': vendor.id})
        with self.assertRaises(UserError):
            tmpl.with_user(self.mp_admin).action_submit_listing()
        with self.assertRaises(ValidationError):
            tmpl.write({'listing_state': 'published'})

    def test_vendor_submit_requires_documents_and_bank(self):
        partner = self.env['res.partner'].create({'name': 'Paperless Vendor'})
        vendor = self.env['emi.vendor'].create({'partner_id': partner.id})
        with self.assertRaises(UserError):
            vendor.with_user(self.mp_admin).action_submit()

    def test_vendor_bank_must_belong_to_vendor(self):
        partner = self.env['res.partner'].create({'name': 'Vendor With Wrong Bank'})
        with self.assertRaises(ValidationError):
            self.env['emi.vendor'].create({
                'partner_id': partner.id,
                'settlement_bank_account_id': self.vendor_bank.id,
            })

    def test_commission_bounds(self):
        with self.assertRaises(ValidationError):
            self.vendor.commission_value = 150.0

    def test_finance_reviewer_cannot_read_vendors(self):
        with self.assertRaises(AccessError):
            self.vendor.with_user(self.reviewer).read(['settlement_bank_account_id'])


@tagged('post_install', '-at_install')
class TestEmiFinanceConfig(EmiCommon):

    def test_marketplace_company_cannot_be_finance_company(self):
        with self.assertRaises(ValidationError):
            self.env['emi.finance.company'].create({'code': 'MKT', 'company_id': self.marketplace.id})

    def test_only_one_marketplace_company(self):
        with self.assertRaises(ValidationError):
            self.lender_company.emi_is_marketplace = True

    def test_marketplace_flag_cannot_move_to_finance_company(self):
        self.marketplace.emi_is_marketplace = False
        with self.assertRaises(ValidationError):
            self.lender_company.emi_is_marketplace = True
        self.finance.active = False  # an archived finance company still has its books
        with self.assertRaises(ValidationError):
            self.lender_company.emi_is_marketplace = True

    def test_rate_bounds_and_offered_tenure(self):
        with self.assertRaises(Exception):
            with self.cr.savepoint():
                self.rate_18.rate_percent = -1.0
        plan_24 = self.env.ref('emi_finance.tenure_plan_24')
        with self.assertRaises(ValidationError):
            self.env['emi.interest.rate'].create({
                'finance_company_id': self.finance.id, 'tenure_plan_id': plan_24.id,
                'rate_percent': 7.0, 'date_from': '2020-01-01',
            })

    def test_rate_overlap_rejected(self):
        with self.assertRaises(ValidationError):
            self.env['emi.interest.rate'].create({
                'finance_company_id': self.finance.id, 'tenure_plan_id': self.plan_18.id,
                'rate_percent': 5.0, 'date_from': '2025-01-01',
            })

    def test_config_is_manager_only(self):
        with self.assertRaises(AccessError):
            self.rate_18.with_user(self.officer).write({'note': 'officer edit'})
        with self.assertRaises(AccessError):
            self.rate_18.with_user(self.reviewer).write({'note': 'reviewer edit'})
        self.rate_18.with_user(self.manager).write({'note': 'manager edit'})
        # Reviewers only see their own finance company's rates.
        Rate = self.env['emi.interest.rate'].with_user(self.other_reviewer)
        self.assertFalse(Rate.search([('id', '=', self.rate_18.id)]))

    def test_rate_display_name(self):
        self.assertEqual(self.rate_18.display_name, 'LND / 18 months / 7% Reducing Balance (from 2020-01-01)')

    def test_single_default_downpayment_option(self):
        self.env['emi.downpayment.option'].create({
            'product_tmpl_id': self.phone_tmpl.id, 'name': '10%', 'value': 10.0, 'is_default': True,
        })
        with self.assertRaises(ValidationError):
            self.env['emi.downpayment.option'].create({
                'product_tmpl_id': self.phone_tmpl.id, 'name': '20%', 'value': 20.0, 'is_default': True,
            })

    def test_fixed_downpayment_capped_at_price(self):
        option = self.env['emi.downpayment.option'].create({
            'product_tmpl_id': self.phone_tmpl.id, 'name': 'Fixed', 'amount_type': 'fixed', 'value': 500000.0,
        })
        self.assertEqual(option.compute_min_amount(100000.0), 100000.0)

    def test_disbursement_bank_must_be_finance_company_own(self):
        with self.assertRaises(ValidationError):
            self.finance.settlement_bank_account_id = self.vendor_bank
