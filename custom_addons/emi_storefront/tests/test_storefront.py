# -*- coding: utf-8 -*-
import base64
import re

from odoo.tests import HttpCase, tagged
from odoo.tests.common import new_test_user

from odoo.addons.emi_application.tests.common import EmiCommon

PNG = base64.b64decode(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGNgYGAAAAAEAAH2FzhVAAAAAElFTkSuQmCC'
)


@tagged('post_install', '-at_install')
class TestEmiStorefront(EmiCommon, HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.brand = cls.env['emi.phone.brand'].create({'name': 'Samsung'})
        cls.phone_tmpl.emi_brand_id = cls.brand
        cls.draft_phone = cls.env['product.template'].create({
            'name': 'Unreleased Phone', 'list_price': 50000.0, 'vendor_id': cls.vendor.id,
        })
        cls.slug = cls.env['ir.http']._slug(cls.phone_tmpl)

    def _csrf(self, url):
        page = self.url_open(url)
        self.assertEqual(page.status_code, 200, url)
        return re.search(r'name="csrf_token" value="([^"]+)"', page.text).group(1), page

    def _apply_data(self, token, **overrides):
        data = {
            'csrf_token': token, 'variant_id': self.phone.id,
            'finance_company_id': self.finance.id, 'tenure_plan_id': self.plan_18.id,
            'down_payment_amount': '10000', 'full_name': 'Ram Bahadur', 'date_of_birth': '1990-01-01',
            'phone': '9800000000', 'citizenship_no': '12-34-56', 'permanent_address': 'Kathmandu',
            'occupation': 'salaried', 'monthly_income': '80000', 'delivery_note': 'Pick up at shop',
            'consent': 'on',
        }
        data.update(overrides)
        return data

    def _files(self, **overrides):
        files = {name: (f'{name}.png', PNG, 'image/png')
                 for name in ('citizenship_front', 'citizenship_back', 'photo', 'income_proof')}
        files.update(overrides)
        return files

    # ------------------------------------------------------------------
    # Catalog
    # ------------------------------------------------------------------

    def test_catalog_shows_only_published_phones_with_emi(self):
        page = self.url_open('/phones')
        self.assertEqual(page.status_code, 200)
        self.assertIn('Galaxy Test 128GB', page.text)
        self.assertNotIn('Unreleased Phone', page.text)
        self.assertIn('EMI from', page.text)
        filtered = self.url_open(f'/phones?brand={self.brand.id}&search=galaxy')
        self.assertIn('Galaxy Test 128GB', filtered.text)
        self.assertNotIn('Galaxy Test 128GB', self.url_open('/phones?search=iphone').text)

    def test_phone_page_and_calculator(self):
        page = self.url_open(f'/phones/{self.slug}')
        self.assertEqual(page.status_code, 200)
        self.assertIn('EMI plans', page.text)
        self.assertIn('Lender Co', page.text)
        calc = self.url_open(f'/phones/{self.slug}?finance={self.finance.id}&tenure={self.plan_18.id}&down_payment=10000')
        self.assertIn('/month', calc.text)
        self.assertIn('for 18 months with Lender Co', calc.text)
        too_much = self.url_open(f'/phones/{self.slug}?finance={self.finance.id}&tenure={self.plan_18.id}&down_payment=100000')
        self.assertIn('must be less than the price', too_much.text)

    def test_unpublished_phone_is_not_found(self):
        slug = self.env['ir.http']._slug(self.draft_phone)
        self.assertEqual(self.url_open(f'/phones/{slug}').status_code, 404)
        self.vendor.with_user(self.mp_admin).action_suspend()
        self.assertEqual(self.url_open(f'/phones/{self.slug}').status_code, 404)

    # ------------------------------------------------------------------
    # Online application
    # ------------------------------------------------------------------

    def test_apply_requires_login(self):
        response = self.url_open(f'/phones/{self.slug}/apply', allow_redirects=False)
        self.assertIn(response.status_code, (302, 303))
        self.assertIn('/web/login', response.headers.get('Location', ''))

    def test_online_application_is_submitted_with_kyc(self):
        self.authenticate(self.customer_user.login, self.customer_user.login + 'x' * max(0, 8 - len(self.customer_user.login)))
        token, _page = self._csrf(f'/phones/{self.slug}/apply')
        response = self.url_open(f'/phones/{self.slug}/apply', data=self._apply_data(token), files=self._files())
        self.assertEqual(response.status_code, 200)
        app = self.env['emi.application'].search([('partner_id', '=', self.customer.id)])
        self.assertEqual(len(app), 1)
        self.assertEqual(app.state, 'submitted')
        self.assertEqual(app.product_id, self.phone)
        self.assertEqual(app.interest_rate_id, self.rate_18)
        self.assertTrue(app.kyc_ids.citizenship_front and app.kyc_ids.income_proof)
        self.assertFalse(app.kyc_ids.verified)
        self.assertIn('submitted', response.url)
        self.assertIn(self.customer_user, self.customer_group.user_ids)

    def test_bad_upload_and_bad_choices_are_rejected(self):
        self.authenticate(self.customer_user.login, self.customer_user.login + 'x' * max(0, 8 - len(self.customer_user.login)))
        token, _page = self._csrf(f'/phones/{self.slug}/apply')
        text_file = self._files(photo=('photo.png', b'not really an image', 'image/png'))
        response = self.url_open(f'/phones/{self.slug}/apply', data=self._apply_data(token), files=text_file)
        self.assertIn('passport-size photo must be', response.text)

        plan_24 = self.env.ref('emi_finance.tenure_plan_24')
        response = self.url_open(f'/phones/{self.slug}/apply', data=self._apply_data(token, tenure_plan_id=plan_24.id),
                                 files=self._files())
        self.assertIn('tenure it offers', response.text)

        response = self.url_open(f'/phones/{self.slug}/apply', data=self._apply_data(token, date_of_birth='2015-01-01'),
                                 files=self._files())
        self.assertIn('at least 18', response.text)
        self.assertFalse(self.env['emi.application'].search([('partner_id', '=', self.customer.id)]))

    # ------------------------------------------------------------------
    # Retailers
    # ------------------------------------------------------------------

    def test_retailer_self_registration(self):
        user = new_test_user(self.env, 'new_retailer', groups='base.group_portal')
        self.authenticate('new_retailer', 'new_retailer')
        token, _page = self._csrf('/retailer/register')
        response = self.url_open('/retailer/register', data={
            'csrf_token': token, 'business_name': 'Pokhara Mobiles', 'pan': '612345678', 'phone': '061-555',
            'street': 'Lakeside', 'city': 'Pokhara', 'bank_name': 'Test Bank', 'account_number': 'ACC-1',
        }, files=[('documents', ('reg.pdf', b'%PDF-1.4 test', 'application/pdf')),
                  ('documents', ('pan.png', PNG, 'image/png'))])
        self.assertEqual(response.status_code, 200)
        vendor = self.env['emi.vendor'].search([('user_ids', 'in', user.id)])
        self.assertEqual(vendor.state, 'pending')
        self.assertEqual(len(vendor.onboarding_document_ids), 2)
        self.assertEqual(vendor.settlement_bank_account_id.acc_number, 'ACC-1')
        self.assertIn(user, self.env.ref('emi_marketplace.group_emi_vendor_portal').user_ids)

    def test_retailer_listings_are_their_own_and_start_as_drafts(self):
        self.authenticate(self.vendor_user.login, self.vendor_user.login)
        token, _page = self._csrf('/my/retailer/listing/new')
        self.url_open('/my/retailer/listing/new', data={
            'csrf_token': token, 'name': 'Redmi Test', 'list_price': '25000', 'brand_id': self.brand.id,
            'listing_state': 'published', 'vendor_id': '999',  # ignored
        }, files={'image': ('phone.png', PNG, 'image/png')})
        listing = self.env['product.template'].search([('name', '=', 'Redmi Test')])
        self.assertEqual(listing.vendor_id, self.vendor)
        self.assertEqual(listing.listing_state, 'draft')
        self.assertTrue(listing.image_1920)

        self.url_open(f'/my/retailer/listing/{listing.id}/submit', data={'csrf_token': token})
        self.assertEqual(listing.listing_state, 'pending_review')

        other_partner = self.env['res.partner'].create({'name': 'Other Retailer'})
        other_vendor = self.env['emi.vendor'].create({'partner_id': other_partner.id})
        foreign = self.env['product.template'].create({'name': 'Not Yours', 'vendor_id': other_vendor.id})
        self.assertEqual(self.url_open(f'/my/retailer/listing/{foreign.id}').status_code, 403)

    def test_retailer_dashboard_hides_customer_until_disbursed(self):
        app = self._draft_application()
        app.with_user(self.officer).action_submit()
        self.authenticate(self.vendor_user.login, self.vendor_user.login)
        page = self.url_open('/my/retailer')
        self.assertEqual(page.status_code, 200)
        self.assertIn(app.name, page.text)
        self.assertNotIn('Ram Bahadur', page.text)
        self.assertIn('After disbursement', page.text)
