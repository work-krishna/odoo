# -*- coding: utf-8 -*-
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import Form, tagged

from .common import DOC, EmiCommon


@tagged('post_install', '-at_install')
class TestEmiApplicationWorkflow(EmiCommon):

    # ------------------------------------------------------------------
    # Creation from the UI and EMI math
    # ------------------------------------------------------------------

    def test_form_created_application_keeps_interest_rate(self):
        """Saving from the form must keep the server-resolved rate (it used to
        be dropped, so every UI submission failed)."""
        with Form(self.env['emi.application'].with_user(self.officer)) as form:
            form.partner_id = self.customer
            form.product_id = self.phone
            form.finance_company_id = self.finance
            form.tenure_plan_id = self.plan_18
            form.down_payment_amount = 10000.0
            form.delivery_note = 'Deliver to office'
            self.assertEqual(form.interest_rate_percent, 7.0)
        app = form.record
        self.assertEqual(app.interest_rate_id, self.rate_18)
        self.assertEqual(app.interest_calc_method, 'reducing')
        self.assertEqual(app.company_id, self.marketplace)
        self.assertEqual(app.vendor_id, self.vendor)

    def test_reducing_and_flat_and_zero_rate_math(self):
        reducing = self._draft_application(plan=self.plan_18, down_payment_amount=0.0)
        self.assertAlmostEqual(reducing.emi_amount, 5868.50, places=2)
        self.assertAlmostEqual(reducing.total_interest_amount, 5632.98, places=1)

        zero = self._draft_application(plan=self.plan_12, down_payment_amount=0.0)
        self.assertAlmostEqual(zero.emi_amount, 100000 / 12, places=2)
        self.assertEqual(zero.total_interest_amount, 0.0)

        flat_rate = self.env['emi.interest.rate'].create({
            'finance_company_id': self.other_finance.id, 'tenure_plan_id': self.plan_18.id,
            'rate_percent': 7.0, 'calc_method': 'flat', 'date_from': '2020-01-01',
        })
        flat = self._draft_application(
            plan=self.plan_18, finance_company_id=self.other_finance.id, down_payment_amount=0.0,
        )
        self.assertEqual(flat.interest_rate_id, flat_rate)
        self.assertAlmostEqual(flat.total_interest_amount, 10500.0, places=2)
        self.assertAlmostEqual(flat.emi_amount, 6138.89, places=2)

    # ------------------------------------------------------------------
    # Full happy path with role separation
    # ------------------------------------------------------------------

    def test_full_workflow_respects_roles(self):
        app = self._draft_application()
        app.with_user(self.officer).action_submit()
        self.assertEqual(app.state, 'submitted')

        with self.assertRaises(AccessError):
            app.with_user(self.reviewer).action_start_review()
        app.with_user(self.officer).action_start_review()

        with self.assertRaises(UserError):
            app.with_user(self.officer).action_send_to_finance()  # KYC not verified yet
        app.with_user(self.officer).action_verify_kyc()
        self.assertTrue(app.kyc_verified)
        app.with_user(self.officer).action_send_to_finance()

        with self.assertRaises(AccessError):
            app.with_user(self.officer).action_approve()
        with self.assertRaises(AccessError):
            app.with_user(self.other_reviewer).action_approve()
        app.with_user(self.reviewer).action_approve()
        self.assertEqual(app.approved_by, self.reviewer)

        with self.assertRaises(AccessError):
            app.with_user(self.officer).action_disburse()
        app.with_user(self.reviewer).action_disburse()
        app.with_user(self.officer).action_activate()
        app.with_user(self.officer).action_close()
        self.assertEqual(app.state, 'closed')

    def test_reject_wizard_needs_reason_and_right_role(self):
        app = self._draft_application()
        app.with_user(self.officer).action_submit()
        app.with_user(self.officer).action_start_review()

        wizard = self.env['emi.application.reject.wizard'].with_user(self.officer).create({
            'application_id': app.id, 'reason': '   ',
        })
        with self.assertRaises(UserError):
            wizard.action_confirm()

        with self.assertRaises(AccessError):
            app.with_user(self.reviewer).action_reject('Not ours to reject yet')

        self.env['emi.application.reject.wizard'].with_user(self.officer).create({
            'application_id': app.id, 'reason': 'Citizenship photo unreadable',
        }).action_confirm()
        self.assertEqual(app.state, 'rejected')
        self.assertEqual(app.rejection_reason, 'Citizenship photo unreadable')

    def test_return_to_draft_clears_kyc_verification(self):
        app = self._draft_application()
        app.with_user(self.officer).action_submit()
        app.with_user(self.officer).action_start_review()
        app.with_user(self.officer).action_verify_kyc()
        app.with_user(self.officer).action_return_to_draft()
        self.assertEqual(app.state, 'draft')
        self.assertFalse(app.kyc_verified)

    # ------------------------------------------------------------------
    # Tampering
    # ------------------------------------------------------------------

    def test_workflow_fields_cannot_be_written_directly(self):
        app = self._draft_application()
        for vals in ({'state': 'approved'}, {'interest_rate_percent': 0.0}, {'approved_by': self.officer.id}):
            with self.assertRaises(AccessError):
                app.with_user(self.officer).write(vals)
        with self.assertRaises(AccessError):
            self.env['emi.application'].with_user(self.officer).create({
                'partner_id': self.customer.id, 'product_id': self.phone.id,
                'finance_company_id': self.finance.id, 'tenure_plan_id': self.plan_18.id,
                'state': 'approved',
            })

    def test_portal_customer_is_read_only(self):
        app = self._draft_application()
        as_customer = app.with_user(self.customer_user)
        self.assertEqual(as_customer.state, 'draft')  # can read own application
        with self.assertRaises(AccessError):
            as_customer.write({'down_payment_amount': 99999.0})
        with self.assertRaises(AccessError):
            as_customer.kyc_ids.write({'phone': '9811111111'})
        with self.assertRaises(AccessError):
            as_customer.action_submit()

    def test_kyc_verified_only_through_workflow(self):
        app = self._draft_application()
        with self.assertRaises(AccessError):
            app.kyc_ids.with_user(self.officer).write({'verified': True})

    def test_kyc_edit_resets_verification(self):
        app = self._draft_application()
        app.with_user(self.officer).action_submit()
        app.with_user(self.officer).action_start_review()
        app.with_user(self.officer).action_verify_kyc()
        app.kyc_ids.with_user(self.officer).write({'citizenship_no': '99-99-99'})
        self.assertFalse(app.kyc_verified)

    def test_one_kyc_per_application(self):
        app = self._draft_application()
        with self.assertRaises(Exception):
            with self.cr.savepoint():
                self.env['emi.kyc'].create(dict(self._kyc_vals(), application_id=app.id))

    def test_terms_frozen_after_submit(self):
        app = self._draft_application()
        app.with_user(self.officer).action_submit()
        with self.assertRaises(UserError):
            app.with_user(self.officer).write({'down_payment_amount': 20000.0})
        with self.assertRaises(UserError):
            app.with_user(self.officer).unlink()

    def test_reviewer_scoped_to_own_finance_company(self):
        app = self._draft_application()
        self.assertFalse(self.env['emi.application'].with_user(self.other_reviewer).search([('id', '=', app.id)]))
        self.assertTrue(self.env['emi.application'].with_user(self.reviewer).search([('id', '=', app.id)]))

    # ------------------------------------------------------------------
    # Submission validation
    # ------------------------------------------------------------------

    def test_submit_requires_complete_kyc_with_income_proof(self):
        app = self._draft_application(kyc_ids=[(0, 0, self._kyc_vals(income_proof=False))])
        with self.assertRaises(UserError):
            app.with_user(self.officer).action_submit()

    def test_submit_enforces_down_payment_minimums(self):
        self.finance.min_down_payment_percent = 20.0
        app = self._draft_application(down_payment_amount=5000.0)
        with self.assertRaises(ValidationError):
            app.with_user(self.officer).action_submit()

        option = self.env['emi.downpayment.option'].create({
            'product_tmpl_id': self.phone_tmpl.id, 'name': '15% Down', 'value': 15.0,
        })
        app = self._draft_application(down_payment_amount=20000.0)
        with self.assertRaises(UserError):  # product has options: one must be chosen
            app.with_user(self.officer).action_submit()
        app.with_user(self.officer).write({'downpayment_option_id': option.id})
        app.with_user(self.officer).action_submit()
        self.assertEqual(app.state, 'submitted')

    def test_submit_rejects_unoffered_tenure_and_suspended_vendor(self):
        plan_24 = self.env.ref('emi_finance.tenure_plan_24')
        app = self._draft_application(plan=plan_24)
        with self.assertRaises(UserError):
            app.with_user(self.officer).action_submit()

        app = self._draft_application()
        self.vendor.with_user(self.mp_admin).action_suspend()
        with self.assertRaises(UserError):
            app.with_user(self.officer).action_submit()

    def test_submit_requires_active_rate(self):
        self.rate_18.date_to = '2020-12-31'
        app = self._draft_application()
        with self.assertRaises(UserError):
            app.with_user(self.officer).action_submit()

    # ------------------------------------------------------------------
    # Snapshots survive configuration changes
    # ------------------------------------------------------------------

    def test_rate_and_tenure_locked_once_used(self):
        app = self._draft_application()
        app.with_user(self.officer).action_submit()
        with self.assertRaises(UserError):
            self.rate_18.with_user(self.manager).write({'rate_percent': 9.0})
        with self.assertRaises(UserError):
            self.plan_18.with_user(self.manager).write({'months': 20})
        with self.assertRaises(UserError):
            self.rate_18.with_user(self.manager).unlink()
        # Closing the period is still allowed.
        self.rate_18.with_user(self.manager).write({'date_to': '2099-12-31'})
        self.assertEqual(app.interest_rate_percent, 7.0)

    def test_vendor_snapshot_not_rewritten(self):
        app = self._draft_application()
        app.with_user(self.officer).action_submit()
        other_partner = self.env['res.partner'].create({'name': 'Other Vendor'})
        other_vendor = self.env['emi.vendor'].create({'partner_id': other_partner.id})
        self.phone_tmpl.with_user(self.mp_admin).action_unpublish_listing()
        self.phone_tmpl.with_user(self.mp_admin).write({'vendor_id': other_vendor.id})
        self.assertEqual(app.vendor_id, self.vendor)


@tagged('post_install', '-at_install')
class TestEmiMenus(EmiCommon):

    def _visible(self, user):
        return self.env['ir.ui.menu'].with_user(user)._visible_menu_ids()

    def test_marketplace_admin_sees_marketplace_menu(self):
        visible = self._visible(self.mp_admin)
        self.assertIn(self.env.ref('emi_finance.menu_emi_root').id, visible)
        self.assertIn(self.env.ref('emi_marketplace.menu_emi_vendor').id, visible)
        self.assertIn(self.env.ref('emi_marketplace.menu_emi_listing_review').id, visible)
        self.assertNotIn(self.env.ref('emi_application.menu_emi_application').id, visible)

    def test_reviewer_menu_scope(self):
        visible = self._visible(self.reviewer)
        self.assertIn(self.env.ref('emi_application.menu_emi_application').id, visible)
        self.assertNotIn(self.env.ref('emi_marketplace.menu_emi_vendor').id, visible)
        self.assertNotIn(self.env.ref('emi_finance.menu_emi_tenure_plan').id, visible)
