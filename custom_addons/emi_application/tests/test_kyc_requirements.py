# -*- coding: utf-8 -*-
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import tagged

from .common import DOC, EmiCommon


@tagged('post_install', '-at_install')
class TestKycRequirements(EmiCommon):
    """Items an EMI Manager adds to the KYC at runtime (KYC Requirements)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.agreement = cls.env.ref('emi_application.kyc_requirement_signed_agreement')
        cls.Requirement = cls.env['emi.kyc.requirement'].with_user(cls.manager)

    def _item(self, app, requirement):
        return app.kyc_ids.item_ids.filtered(lambda i: i.requirement_id == requirement)

    def test_signed_agreement_is_required_and_nid_optional(self):
        app = self._draft_application(kyc_ids=[(0, 0, self._kyc_vals(item_ids=[]))])
        self.assertTrue(self._item(app, self.agreement), "every KYC form gets a line for each active item")
        with self.assertRaisesRegex(UserError, 'Still missing: Signed EMI Application / Agreement Form'):
            app.with_user(self.officer).action_submit()
        self._item(app, self.agreement).with_user(self.officer).write({'value_file': DOC, 'value_filename': 'a.pdf'})
        self.assertFalse(app.kyc_ids.nid_front or app.kyc_ids.nid_back)
        app.with_user(self.officer).action_submit()
        self.assertEqual(app.state, 'submitted')

    def test_manager_adds_and_archives_items_at_runtime(self):
        app = self._draft_application()
        consent = self.Requirement.create({'name': 'Consent Form', 'value_type': 'file', 'required': True})
        self.Requirement.create({'name': 'Reference Person', 'value_type': 'text', 'party': 'guarantor'})
        # Open KYC forms ask for new items right away.
        self.assertEqual(len(app.kyc_ids.item_ids), 3)
        with self.assertRaisesRegex(UserError, 'Consent Form'):
            app.with_user(self.officer).action_submit()
        consent.required = False
        app.with_user(self.officer).action_submit()
        self.assertEqual(app.state, 'submitted')

        consent.write({'required': True, 'active': False})
        later = self._draft_application()
        self.assertFalse(self._item(later, consent), "archived items are no longer asked for")
        later.with_user(self.officer).action_submit()
        consent.active = True
        self.assertTrue(self._item(later, consent), "re-activated items are asked for again while in review")
        with self.assertRaisesRegex(UserError, 'Consent Form'):
            later.with_user(self.officer).action_start_review()
            later.with_user(self.officer).action_verify_kyc()

    def test_item_types_are_checked(self):
        pledge = self.Requirement.create({
            'name': 'Guarantor agrees to stand surety', 'value_type': 'checkbox', 'party': 'guarantor', 'required': True,
        })
        income = self.Requirement.create({'name': 'Other monthly income', 'value_type': 'number'})
        issued = self.Requirement.create({'name': 'Guarantor citizenship issue date', 'value_type': 'date', 'required': True})
        app = self._draft_application()
        with self.assertRaises(UserError) as caught:
            app.with_user(self.officer).action_submit()
        self.assertIn('Guarantor agrees to stand surety', str(caught.exception))
        self.assertIn('Guarantor citizenship issue date', str(caught.exception))
        with self.assertRaises(ValidationError):
            self._item(app, income).with_user(self.officer).value_text = 'a lot'
        self._item(app, income).with_user(self.officer).value_text = '0'
        self._item(app, pledge).with_user(self.officer).value_bool = True
        self._item(app, issued).with_user(self.officer).value_date = '2010-05-01'
        self.assertEqual(self._item(app, pledge).value_display, 'Yes')
        app.with_user(self.officer).action_submit()
        self.assertEqual(app.state, 'submitted')

    def test_only_managers_configure_and_answers_are_kept(self):
        with self.assertRaises(AccessError):
            self.env['emi.kyc.requirement'].with_user(self.officer).create({'name': 'Anything'})
        unused = self.Requirement.create({'name': 'Unused'})
        answered = self.Requirement.create({'name': 'Bank Statement'})
        app = self._draft_application()
        self._item(app, answered).with_user(self.officer).write({'value_file': DOC, 'value_filename': 'bank.pdf'})
        with self.assertRaises(UserError):
            answered.value_type = 'text'
        with self.assertRaises(UserError):
            answered.unlink()
        answered.action_archive()
        self.assertTrue(self._item(app, answered).has_value, "archiving keeps the answers")
        unused.unlink()  # its empty lines go with it
        self.assertFalse(app.kyc_ids.item_ids.filtered(lambda i: i.name == 'Unused'))

    def test_item_edit_rules(self):
        app = self._draft_application()
        item = self._item(app, self.agreement).with_user(self.officer)
        with self.assertRaises(AccessError):
            item.requirement_id = self.Requirement.create({'name': 'Other'})
        with self.assertRaises(UserError):
            item.unlink()

        officer_app = app.with_user(self.officer)
        officer_app.action_submit()
        officer_app.action_start_review()
        officer_app.action_verify_kyc()
        item.value_file = DOC
        self.assertFalse(app.kyc_verified, "a replaced document needs checking again")
        officer_app.action_verify_kyc()
        officer_app.action_send_to_finance()
        with self.assertRaises(UserError):
            item.value_filename = 'late.pdf'

    def test_reviewer_sees_items_once_sent(self):
        app = self._draft_application()
        Item = self.env['emi.kyc.item'].with_user(self.reviewer)
        self.assertFalse(Item.search([('kyc_id', '=', app.kyc_ids.id)]))
        officer_app = app.with_user(self.officer)
        officer_app.action_submit()
        officer_app.action_start_review()
        officer_app.action_verify_kyc()
        officer_app.action_send_to_finance()
        self.assertEqual(Item.search([('kyc_id', '=', app.kyc_ids.id)]).value_filename, 'agreement.pdf')
        self.assertFalse(self.env['emi.kyc.item'].with_user(self.other_reviewer).search([('kyc_id', '=', app.kyc_ids.id)]))

    def test_new_kyc_form_lists_configured_items(self):
        consent = self.Requirement.create({'name': 'Consent Form', 'required': True})
        defaults = self.env['emi.kyc'].with_user(self.officer).default_get(['item_ids'])
        self.assertEqual([command[2]['requirement_id'] for command in defaults['item_ids']],
                         [self.agreement.id, consent.id])
        vals = self._kyc_vals()
        del vals['item_ids']
        app = self._draft_application(kyc_ids=[(0, 0, vals)])
        self.assertEqual(app.kyc_ids.item_ids.requirement_id, self.agreement | consent)
