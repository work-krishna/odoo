# -*- coding: utf-8 -*-
import re

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
        with self.assertRaises(AccessError):
            app.with_user(self.other_reviewer).action_disburse()

    def test_disburse_to_close_without_accounting(self):
        if self.env['ir.module.module']._get('emi_accounting').state == 'installed':
            self.skipTest("emi_accounting posts entries on disbursement; covered by its own tests")
        app = self._draft_application()
        officer_app = app.with_user(self.officer)
        officer_app.action_submit()
        officer_app.action_start_review()
        officer_app.action_verify_kyc()
        officer_app.action_send_to_finance()
        app.with_user(self.reviewer).action_approve()
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

    def test_defaults_cannot_prefill_workflow_fields(self):
        """Context keys and user defaults must not create an application
        that skips submission, KYC review or the lender's approval."""
        vals = {
            'partner_id': self.customer.id, 'product_id': self.phone.id,
            'finance_company_id': self.finance.id, 'tenure_plan_id': self.plan_18.id,
            'down_payment_amount': 10000.0, 'delivery_note': 'Deliver to office',
        }
        defaults = {
            'default_state': 'pending_finance_approval', 'default_approved_by': self.reviewer.id,
            'default_approved_date': '2024-01-01 00:00:00', 'default_reviewed_by': self.officer.id,
            'default_sent_to_finance_date': '2024-01-01 00:00:00', 'default_rejection_reason': 'x',
            'default_financed_amount': 5000.0, 'default_interest_rate_percent': 0.0,
        }
        App = self.env['emi.application'].with_user(self.officer)
        if 'disbursement_date' in App._fields:  # emi_accounting's server fields
            defaults.update(default_disbursement_date='2024-01-01', default_commission_amount=1.0)
        app = App.with_context(**defaults).create(dict(vals))
        self.assertEqual(app.state, 'draft')
        self.assertFalse(app.approved_by or app.approved_date or app.reviewed_by or app.sent_to_finance_date)
        self.assertFalse(app.rejection_reason)
        self.assertEqual(app.financed_amount, 90000.0)
        self.assertEqual(app.interest_rate_percent, 7.0)
        if 'disbursement_date' in App._fields:
            self.assertFalse(app.disbursement_date)
            self.assertFalse(app.commission_amount)

        self.env['ir.default'].with_user(self.officer).set('emi.application', 'state', 'approved', user_id=True)
        self.assertEqual(App.create(dict(vals)).state, 'draft')

    def test_computed_amounts_cannot_be_written(self):
        app = self._draft_application()
        app.with_user(self.officer).action_submit()
        app.with_user(self.officer).action_start_review()
        eur = self.env.ref('base.EUR')
        for vals in ({'financed_amount': 5000.0}, {'emi_amount': 1.0}, {'total_payable_amount': 1.0},
                     {'total_interest_amount': 0.0}, {'currency_id': eur.id}, {'sent_to_finance_date': False}):
            with self.assertRaises(AccessError):
                app.with_user(self.officer).write(vals)
        self.assertEqual(app.financed_amount, 90000.0)

    def test_kyc_defaults_cannot_verify_or_attach_late(self):
        app = self._draft_application(kyc_ids=[])
        Kyc = self.env['emi.kyc'].with_user(self.officer)
        kyc = Kyc.with_context(default_verified=True, default_consent_date='2024-01-01 00:00:00').create(
            dict(self._kyc_vals(), application_id=app.id))
        self.assertFalse(kyc.verified)
        self.assertFalse(kyc.consent_date)
        with self.assertRaises(AccessError):
            kyc.write({'consent_date': '2024-01-01 00:00:00'})

        late = self._draft_application(kyc_ids=[])
        late.sudo().write({'state': 'kyc_review'})
        with self.assertRaises(UserError):
            Kyc.with_context(default_application_id=late.id).create(self._kyc_vals())
        self.env['ir.default'].with_user(self.officer).set('emi.kyc', 'application_id', late.id, user_id=True)
        with self.assertRaises(UserError):
            Kyc.create(self._kyc_vals())

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

    def test_kyc_income_and_guarantor_edits_reset_verification(self):
        app = self._draft_application()
        officer_app = app.with_user(self.officer)
        officer_app.action_submit()
        officer_app.action_start_review()
        for vals in ({'monthly_income': 500000}, {'occupation': 'business'}, {'employer_name': 'Other Co'},
                     {'bank_name': 'Other Bank'}, {'guarantor_name': 'Someone Else'},
                     {'guarantor_citizenship_front': DOC}, {'guarantor_nid_front': DOC}, {'guarantor_photo': DOC},
                     {'nid_front': DOC}, {'nid_back': DOC}):
            officer_app.action_verify_kyc()
            app.kyc_ids.with_user(self.officer).write(vals)
            self.assertFalse(app.kyc_verified, vals)
        officer_app.action_verify_kyc()
        app.kyc_ids.with_user(self.officer).write({'temporary_address': 'Lalitpur', 'email': 'ram@example.com'})
        self.assertTrue(app.kyc_verified)

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
        app.with_user(self.officer).action_submit()
        app.with_user(self.officer).action_start_review()
        app.with_user(self.officer).action_verify_kyc()
        app.with_user(self.officer).action_send_to_finance()
        self.assertFalse(self.env['emi.application'].with_user(self.other_reviewer).search([('id', '=', app.id)]))
        self.assertTrue(self.env['emi.application'].with_user(self.reviewer).search([('id', '=', app.id)]))

    def test_reviewer_sees_only_applications_sent_to_them(self):
        """Lender staff get an application and its KYC documents only once the
        marketplace sends it; their own rejections stay visible."""
        App = self.env['emi.application'].with_user(self.reviewer)
        Kyc = self.env['emi.kyc'].with_user(self.reviewer)
        draft = self._draft_application()
        kyc_rejected = self._draft_application()
        kyc_rejected.with_user(self.officer).action_submit()
        kyc_rejected.with_user(self.officer).action_start_review()
        kyc_rejected.with_user(self.officer).action_reject('Citizenship photo unreadable')
        for app in (draft, kyc_rejected):
            self.assertFalse(App.search([('id', '=', app.id)]))
            self.assertFalse(Kyc.search([('application_id', '=', app.id)]))
            with self.assertRaises(AccessError):
                app.kyc_ids.with_user(self.reviewer).read(['photo'])

        sent = self._draft_application()
        sent.with_user(self.officer).action_submit()
        sent.with_user(self.officer).action_start_review()
        sent.with_user(self.officer).action_verify_kyc()
        sent.with_user(self.officer).action_send_to_finance()
        self.assertTrue(sent.sent_to_finance_date)
        sent.with_user(self.reviewer).action_reject('Income too low')
        self.assertEqual(App.search([('id', '=', sent.id)]).state, 'rejected')
        self.assertTrue(Kyc.search([('application_id', '=', sent.id)]).photo)

    # ------------------------------------------------------------------
    # Submission validation
    # ------------------------------------------------------------------

    def test_submit_requires_complete_kyc_with_income_proof(self):
        app = self._draft_application(kyc_ids=[(0, 0, self._kyc_vals(income_proof=False))])
        with self.assertRaisesRegex(UserError, 'Still missing: Income Proof'):
            app.with_user(self.officer).action_submit()

    def test_signed_application_form_is_required_and_consent_optional(self):
        app = self._draft_application(application_form=False)
        officer_app = app.with_user(self.officer)
        with self.assertRaisesRegex(UserError, 'EMI application form'):
            officer_app.action_submit()
        officer_app.write({'application_form': DOC, 'application_form_filename': 'form.pdf'})
        self.assertFalse(app.consent_form)
        officer_app.action_submit()
        with self.assertRaisesRegex(UserError, 'only be changed while the application is a draft'):
            officer_app.write({'consent_form': DOC})
        # Applications submitted before the form was required do not reach the lender without it.
        app.sudo().application_form = False
        officer_app.action_start_review()
        officer_app.action_verify_kyc()
        with self.assertRaisesRegex(UserError, 'EMI application form'):
            officer_app.action_send_to_finance()

    def test_submit_requires_guarantor_documents_but_not_nid(self):
        for field in ('guarantor_name', 'guarantor_phone', 'guarantor_relation', 'guarantor_citizenship_front',
                      'guarantor_citizenship_back', 'guarantor_photo'):
            app = self._draft_application(kyc_ids=[(0, 0, self._kyc_vals(**{field: False}))])
            label = self.env['emi.kyc']._fields[field].string
            with self.assertRaisesRegex(UserError, re.escape(label)):
                app.with_user(self.officer).action_submit()
        # Uploading the missing document afterwards is seen at once (same transaction).
        app.kyc_ids.with_user(self.officer).guarantor_photo = DOC
        app.with_user(self.officer).action_submit()
        self.assertEqual(app.state, 'submitted')
        app = self._draft_application()
        self.assertFalse(app.kyc_ids.guarantor_nid_front or app.kyc_ids.guarantor_nid_back)
        app.with_user(self.officer).action_submit()
        self.assertEqual(app.state, 'submitted')

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

    def test_submit_rejects_archived_terms(self):
        zero_down = self.env['emi.downpayment.option'].create({
            'product_tmpl_id': self.phone_tmpl.id, 'name': '0% Down', 'value': 0.0,
        })
        self.env['emi.downpayment.option'].create({
            'product_tmpl_id': self.phone_tmpl.id, 'name': '20% Down', 'value': 20.0,
        })
        app = self._draft_application(down_payment_amount=0.0, downpayment_option_id=zero_down.id)
        zero_down.active = False
        with self.assertRaises(UserError):
            app.with_user(self.officer).action_submit()
        zero_down.active = True

        # other_finance offers every tenure, so only the archive check stops it.
        self.env['emi.interest.rate'].create({
            'finance_company_id': self.other_finance.id, 'tenure_plan_id': self.plan_18.id,
            'rate_percent': 7.0, 'date_from': '2020-01-01',
        })
        any_tenure = self._draft_application(finance_company_id=self.other_finance.id)
        self.plan_18.active = False
        with self.assertRaises(UserError):
            any_tenure.with_user(self.officer).action_submit()
        self.plan_18.active = True

        self.phone_tmpl.active = False
        with self.assertRaises(UserError):
            app.with_user(self.officer).action_submit()
        self.phone_tmpl.active = True
        app.with_user(self.officer).action_submit()
        self.assertEqual(app.state, 'submitted')

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
