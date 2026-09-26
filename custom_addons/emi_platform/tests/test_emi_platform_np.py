# -*- coding: utf-8 -*-
import base64
from unittest.mock import patch

from odoo.tests import tagged
from odoo.tests.common import new_test_user

from odoo.addons.account.tests.common import AccountTestInvoicingCommon

DOC = base64.b64encode(b'doc')
POST = 'odoo.addons.l10n_np_ird.models.account_move.requests.post'


class FakeResponse:
    text = '200'
    status_code = 200


@tagged('post_install_l10n', 'post_install', '-at_install')
class TestEmiPlatformNepal(AccountTestInvoicingCommon):
    """End to end on Nepali books: the marketplace's commission invoice to
    the retailer carries IRD fiscal-year numbering, 13% VAT and goes to CBMS."""

    @classmethod
    @AccountTestInvoicingCommon.setup_country('np')
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env(su=True)
        cls.marketplace = cls.company_data['company']
        env['res.company'].search([('emi_is_marketplace', '=', True)]).emi_is_marketplace = False
        cls.marketplace.write({
            'emi_is_marketplace': True, 'vat': '600000001',
            'l10n_np_cbms_enabled': True, 'l10n_np_cbms_url': 'https://cbms.test',
            'l10n_np_cbms_username': 'u', 'l10n_np_cbms_password': 'p',
        })
        cls.lender = cls.setup_other_company(name='Nepal Finance Ltd')['company']
        plan = env.ref('emi_finance.tenure_plan_12')
        cls.finance = env['emi.finance.company'].create({'code': 'NFL', 'company_id': cls.lender.id})
        env['emi.interest.rate'].create({
            'finance_company_id': cls.finance.id, 'tenure_plan_id': plan.id,
            'rate_percent': 0.0, 'date_from': '2020-01-01',
        })
        (cls.marketplace | cls.lender).action_emi_setup_accounting()

        cls.officer = new_test_user(env, 'np_officer', groups='emi_finance.group_emi_officer',
                                    company_id=cls.marketplace.id, company_ids=[(6, 0, cls.marketplace.ids)])
        cls.reviewer = new_test_user(env, 'np_reviewer', groups='emi_finance.group_emi_finance_reviewer',
                                     company_id=cls.lender.id, company_ids=[(6, 0, cls.lender.ids)])
        retailer = env['res.partner'].create({'name': 'Kathmandu Mobiles', 'is_company': True, 'vat': '300000009'})
        bank = env['res.partner.bank'].create({'acc_number': 'NP-KM-1', 'partner_id': retailer.id})
        vendor = env['emi.vendor'].create({'partner_id': retailer.id, 'settlement_bank_account_id': bank.id,
                                           'commission_value': 4.0})
        vendor.onboarding_document_ids = [(0, 0, {'name': 'r.pdf', 'datas': DOC, 'res_model': 'emi.vendor',
                                                  'res_id': vendor.id})]
        vendor.action_submit()
        vendor.action_approve()
        tmpl = env['product.template'].create({'name': 'Phone NP', 'list_price': 50000.0, 'vendor_id': vendor.id})
        tmpl.action_submit_listing()
        tmpl.action_publish_listing()
        cls.app_vals = {
            'partner_id': env['res.partner'].create({'name': 'Hari'}).id,
            'product_id': tmpl.product_variant_id.id, 'finance_company_id': cls.finance.id,
            'tenure_plan_id': plan.id, 'delivery_note': 'x',
            'kyc_ids': [(0, 0, {
                'full_name': 'Hari', 'date_of_birth': '1990-01-01', 'phone': '98', 'citizenship_no': 'C',
                'permanent_address': 'Lalitpur', 'occupation': 'business', 'monthly_income': 90000,
                'citizenship_front': DOC, 'citizenship_back': DOC, 'photo': DOC, 'income_proof': DOC,
                'guarantor_name': 'Gita', 'guarantor_phone': '9811111111', 'guarantor_relation': 'Sister',
                'guarantor_citizenship_front': DOC, 'guarantor_citizenship_back': DOC, 'guarantor_photo': DOC,
                'item_ids': [(0, 0, {
                    'requirement_id': env.ref('emi_application.kyc_requirement_signed_agreement').id,
                    'value_file': DOC, 'value_filename': 'agreement.pdf',
                })],
            })],
        }

    def test_commission_invoice_is_ird_numbered_and_sent_to_cbms(self):
        app = self.env['emi.application'].with_user(self.officer).create(self.app_vals)
        officer_app = app.with_user(self.officer)
        officer_app.action_submit()
        officer_app.action_start_review()
        officer_app.action_verify_kyc()
        officer_app.action_send_to_finance()
        app.with_user(self.reviewer).action_approve()
        with patch(POST, return_value=FakeResponse()) as post:
            app.with_user(self.reviewer).action_disburse()
            invoice = app.commission_invoice_id
            self.assertEqual(invoice.l10n_np_cbms_state, 'to_send')
            self.env['account.move']._cron_l10n_np_cbms_sync()
        self.assertRegex(invoice.name, r'/\d{4}-\d{2}/0001$')
        self.assertEqual(invoice.l10n_np_cbms_state, 'sent')
        payload = post.call_args.kwargs['json']
        self.assertEqual(payload['buyer_pan'], '300000009')
        self.assertEqual(payload['taxable_sales_vat'], 2000.0)  # 4% of 50,000
        self.assertEqual(payload['vat'], 260.0)                  # 13% VAT on the commission
        # The customer's phone is invoiced by the retailer, not the marketplace.
        self.assertFalse(self.env['account.move'].search([
            ('emi_application_id', '=', app.id), ('move_type', '=', 'out_invoice'),
            ('partner_id', '=', app.partner_id.id),
        ]))
