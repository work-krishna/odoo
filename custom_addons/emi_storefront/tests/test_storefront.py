# -*- coding: utf-8 -*-
import base64
import html
import re

from odoo.tests import HttpCase, tagged
from odoo.tests.common import new_test_user

from odoo.addons.emi_application.tests.common import EmiCommon

PNG = base64.b64decode(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGNgYGAAAAAEAAH2FzhVAAAAAElFTkSuQmCC'
)
PDF = b'%PDF-1.4\n1 0 obj << /Type /Catalog >> endobj\ntrailer << /Root 1 0 R >>\n%%EOF\n'


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
            'guarantor_name': 'Shyam Bahadur', 'guarantor_phone': '9811111111', 'guarantor_relation': 'Brother',
            'consent': 'on',
        }
        data.update(overrides)
        return data

    def _files(self, **overrides):
        files = {name: (f'{name}.png', PNG, 'image/png')
                 for name in ('citizenship_front', 'citizenship_back', 'photo', 'income_proof',
                              'guarantor_citizenship_front', 'guarantor_citizenship_back', 'guarantor_photo')}
        agreement = self.env.ref('emi_application.kyc_requirement_signed_agreement')
        files[f'kyc_item_{agreement.id}'] = ('agreement.pdf', PDF, 'application/pdf')
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

    def test_archived_phone_is_not_found(self):
        self.phone_tmpl.active = False
        self.assertEqual(self.phone_tmpl.listing_state, 'published')
        self.assertEqual(self.url_open(f'/phones/{self.slug}').status_code, 404)
        self.assertNotIn('Galaxy Test 128GB', self.url_open('/phones').text)

    def test_phone_photos_are_served_to_visitors(self):
        self.phone_tmpl.image_1920 = base64.b64encode(PNG)
        self.draft_phone.image_1920 = base64.b64encode(PNG)
        tmpl_image = base64.b64decode(self.phone_tmpl.image_512)
        variant_image = base64.b64decode(self.phone.image_1024)
        for login in (None, self.customer_user.login):
            if login:
                self.authenticate(login, login + 'x' * max(0, 8 - len(login)))
            page = self.url_open(f'/web/image/product.template/{self.phone_tmpl.id}/image_512')
            self.assertEqual(page.content, tmpl_image, login)
            page = self.url_open(f'/web/image/product.product/{self.phone.id}/image_1024')
            self.assertEqual(page.content, variant_image, login)
            # Drafts keep the placeholder.
            page = self.url_open(f'/web/image/product.template/{self.draft_phone.id}/image_512')
            self.assertNotEqual(page.content, base64.b64decode(self.draft_phone.image_512), login)
        public = self.env.ref('base.public_user')
        self.assertFalse(self.phone_tmpl.with_user(public)._can_return_content('name'))

    def test_malformed_numbers_do_not_break_the_calculator(self):
        for value in ('nan', 'inf', '1e309'):
            page = self.url_open(
                f'/phones/{self.slug}?finance={self.finance.id}&tenure={self.plan_18.id}&down_payment={value}')
            self.assertEqual(page.status_code, 200, value)
            self.assertIn('for 18 months with Lender Co', page.text)

    def test_calculator_passes_the_down_payment_option_it_used(self):
        Option = self.env['emi.downpayment.option']
        Option.create({'product_tmpl_id': self.phone_tmpl.id, 'name': 'Min 20%', 'value': 20.0, 'sequence': 1})
        ten = Option.create({'product_tmpl_id': self.phone_tmpl.id, 'name': 'Min 10%', 'value': 10.0,
                             'sequence': 2, 'is_default': True})
        page = self.url_open(f'/phones/{self.slug}?finance={self.finance.id}&tenure={self.plan_18.id}&down_payment=10000')
        self.assertIn(f'downpayment_option_id={ten.id}', page.text)

        self.authenticate(self.customer_user.login, self.customer_user.login + 'x' * max(0, 8 - len(self.customer_user.login)))
        form = self.url_open(f'/phones/{self.slug}/apply')
        # The default option, not the first one.
        self.assertRegex(form.text, rf'<option value="{ten.id}" selected="[^"]+">Min 10%</option>')
        self.assertNotRegex(form.text, r'<option value="\d+" selected="[^"]+">Min 20%</option>')
        token = re.search(r'name="csrf_token" value="([^"]+)"', form.text).group(1)
        response = self.url_open(f'/phones/{self.slug}/apply', files=self._files(),
                                 data=self._apply_data(token, downpayment_option_id=ten.id))
        self.assertIn('submitted', response.url)

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
        kyc = app.kyc_ids
        self.assertEqual((kyc.guarantor_name, kyc.guarantor_relation), ('Shyam Bahadur', 'Brother'))
        self.assertTrue(kyc.guarantor_citizenship_front and kyc.guarantor_citizenship_back and kyc.guarantor_photo)
        self.assertEqual(kyc.guarantor_photo_filename, 'guarantor_photo.png')
        self.assertFalse(kyc.guarantor_nid_front or kyc.guarantor_nid_back or kyc.nid_front or kyc.nid_back)
        agreement = self.env.ref('emi_application.kyc_requirement_signed_agreement')
        self.assertEqual(kyc.item_ids.filtered(lambda i: i.requirement_id == agreement).value_filename, 'agreement.pdf')
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

    def test_guarantor_documents_are_required_but_nid_is_optional(self):
        self.authenticate(self.customer_user.login, self.customer_user.login + 'x' * max(0, 8 - len(self.customer_user.login)))
        token, page = self._csrf(f'/phones/{self.slug}/apply')
        self.assertIn('name="guarantor_photo"', page.text)
        self.assertIn('name="guarantor_nid_back"', page.text)
        url = f'/phones/{self.slug}/apply'

        files = self._files()
        del files['guarantor_photo']
        response = self.url_open(url, data=self._apply_data(token), files=files)
        self.assertIn("Please upload the guarantor's passport-size photo.", html.unescape(response.text))
        data = self._apply_data(token)
        del data['guarantor_relation']
        response = self.url_open(url, data=data, files=self._files())
        self.assertIn('Please fill in: guarantor relation', response.text)
        response = self.url_open(url, data=self._apply_data(token),
                                 files=self._files(guarantor_nid_front=('nid.txt', b'plain text', 'text/plain')))
        self.assertIn("front of your guarantor's national ID card must be", html.unescape(response.text))
        self.assertFalse(self.env['emi.application'].search([('partner_id', '=', self.customer.id)]))

        response = self.url_open(url, data=self._apply_data(token), files=self._files(
            guarantor_nid_front=('nid_front.png', PNG, 'image/png'), guarantor_nid_back=('nid_back.png', PNG, 'image/png'),
        ))
        self.assertIn('submitted', response.url)
        kyc = self.env['emi.application'].search([('partner_id', '=', self.customer.id)]).kyc_ids
        self.assertEqual((kyc.guarantor_nid_front_filename, kyc.guarantor_nid_back_filename), ('nid_front.png', 'nid_back.png'))

    def test_configured_kyc_items_on_the_online_form(self):
        Requirement = self.env['emi.kyc.requirement']
        consent = Requirement.create({
            'name': 'Consent Form', 'description': 'Sign it and upload a scan.',
            'template': base64.b64encode(PDF), 'template_filename': 'consent.pdf',
        })
        pan = Requirement.create({'name': 'Employer PAN', 'value_type': 'number', 'required': True})
        pledge = Requirement.create({
            'name': 'Guarantor agrees to stand surety', 'value_type': 'checkbox', 'party': 'guarantor', 'required': True,
        })
        self.authenticate(self.customer_user.login, self.customer_user.login + 'x' * max(0, 8 - len(self.customer_user.login)))
        url = f'/phones/{self.slug}/apply'
        token, page = self._csrf(url)
        for requirement in (consent, pan, pledge):
            self.assertIn(f'name="kyc_item_{requirement.id}"', page.text)
        self.assertIn('Sign it and upload a scan.', page.text)
        self.assertEqual(self.url_open(f'/phones/kyc-form/{consent.id}').content, PDF)
        self.assertEqual(self.url_open(f'/phones/kyc-form/{pan.id}').status_code, 404)

        ticked = {f'kyc_item_{pledge.id}': 'on'}
        response = self.url_open(url, data=self._apply_data(token, **ticked), files=self._files())
        self.assertIn('Please fill in: Employer PAN', response.text)
        response = self.url_open(url, data=self._apply_data(token, **ticked, **{f'kyc_item_{pan.id}': 'lots'}),
                                 files=self._files())
        self.assertIn('Enter Employer PAN as a number', response.text)
        response = self.url_open(url, data=self._apply_data(token, **{f'kyc_item_{pan.id}': '600123456'}),
                                 files=self._files())
        self.assertIn('Please tick: Guarantor agrees to stand surety', response.text)
        self.assertIn('value="600123456"', response.text, "answers are kept when the form comes back")
        agreement = self.env.ref('emi_application.kyc_requirement_signed_agreement')
        files = self._files()
        del files[f'kyc_item_{agreement.id}']
        response = self.url_open(url, data=self._apply_data(token, **ticked, **{f'kyc_item_{pan.id}': '600123456'}),
                                 files=files)
        self.assertIn('Please upload the Signed EMI Application / Agreement Form.', response.text)
        self.assertFalse(self.env['emi.application'].search([('partner_id', '=', self.customer.id)]))

        response = self.url_open(url, data=self._apply_data(token, **ticked, **{f'kyc_item_{pan.id}': '600123456'}),
                                 files=self._files())
        self.assertIn('submitted', response.url)
        items = self.env['emi.application'].search([('partner_id', '=', self.customer.id)]).kyc_ids.item_ids
        answers = {item.requirement_id: item for item in items}
        self.assertEqual(answers[pan].value_text, '600123456')
        self.assertTrue(answers[pledge].value_bool)
        self.assertFalse(answers[consent].has_value, "the consent form was optional")
        self.assertTrue(answers[agreement].has_value)

    def test_malformed_application_input_is_a_form_error(self):
        self.authenticate(self.customer_user.login, self.customer_user.login + 'x' * max(0, 8 - len(self.customer_user.login)))
        token, _page = self._csrf(f'/phones/{self.slug}/apply')
        url = f'/phones/{self.slug}/apply'
        for field in ('down_payment_amount', 'monthly_income'):
            response = self.url_open(url, data=self._apply_data(token, **{field: 'nan'}), files=self._files())
            self.assertEqual(response.status_code, 200, field)
            self.assertIn('alert-danger', response.text, field)
        # A file sent under a text field's name counts as an empty field.
        data = self._apply_data(token)
        del data['full_name']
        response = self.url_open(url, data=data, files=self._files(full_name=('name.txt', b'Ram', 'text/plain')))
        self.assertEqual(response.status_code, 200)
        self.assertIn('Please fill in: full name', response.text)
        self.assertFalse(self.env['emi.application'].search([('partner_id', '=', self.customer.id)]))
        response = self.url_open(url, data=self._apply_data(token),
                                 files=self._files(delivery_street=('street.txt', b'Lakeside', 'text/plain')))
        self.assertIn('submitted', response.url)

    def test_application_requires_and_records_consent(self):
        self.authenticate(self.customer_user.login, self.customer_user.login + 'x' * max(0, 8 - len(self.customer_user.login)))
        token, _page = self._csrf(f'/phones/{self.slug}/apply')
        data = self._apply_data(token)
        del data['consent']
        response = self.url_open(f'/phones/{self.slug}/apply', data=data, files=self._files())
        self.assertIn('agree to their verification', response.text)
        self.assertFalse(self.env['emi.application'].search([('partner_id', '=', self.customer.id)]))

        self.url_open(f'/phones/{self.slug}/apply', data=self._apply_data(token), files=self._files())
        app = self.env['emi.application'].search([('partner_id', '=', self.customer.id)])
        self.assertEqual(app.state, 'submitted')
        self.assertTrue(app.kyc_ids.consent_date)

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

    def test_archived_retailer_cannot_register_again(self):
        self.vendor.active = False
        self.authenticate(self.vendor_user.login, self.vendor_user.login)
        page = self.url_open('/retailer/register')
        self.assertIn('has been closed', page.text)
        self.assertNotIn('name="business_name"', page.text)
        token, _page = self._csrf('/my/security')
        self.url_open('/retailer/register', data={
            'csrf_token': token, 'business_name': 'Second Shop', 'pan': '600000001', 'phone': '01-555',
            'street': 'New Road', 'account_number': 'ACC-2',
        }, files=[('documents', ('reg.pdf', b'%PDF-1.4 test', 'application/pdf'))])
        Vendor = self.env['emi.vendor'].with_context(active_test=False)
        self.assertEqual(Vendor.search([('user_ids', 'in', self.vendor_user.id)]), self.vendor)
        self.assertIn('has been closed', self.url_open('/my/retailer').text)

    def test_retailer_registration_ignores_files_in_text_fields(self):
        new_test_user(self.env, 'file_retailer', groups='base.group_portal')
        self.authenticate('file_retailer', 'file_retailer')
        token, _page = self._csrf('/retailer/register')
        response = self.url_open('/retailer/register', data={
            'csrf_token': token, 'pan': '612345678', 'phone': '061-555', 'street': 'Lakeside', 'account_number': 'ACC-1',
        }, files=[('business_name', ('name.txt', b'Shop', 'text/plain')),
                  ('documents', ('reg.pdf', b'%PDF-1.4 test', 'application/pdf'))])
        self.assertEqual(response.status_code, 200)
        self.assertIn('Please fill in: business name', response.text)

    def test_listing_price_must_be_a_real_number(self):
        self.authenticate(self.vendor_user.login, self.vendor_user.login)
        token, _page = self._csrf('/my/retailer/listing/new')
        for price in ('nan', 'inf', 'infinity', '1e309'):
            response = self.url_open('/my/retailer/listing/new', data={
                'csrf_token': token, 'name': f'Bad Price {price}', 'list_price': price,
            })
            self.assertEqual(response.status_code, 200, price)
            self.assertIn('price (VAT included)', response.text, price)
        response = self.url_open('/my/retailer/listing/new', data={'csrf_token': token, 'list_price': '100'},
                                 files={'name': ('name.txt', b'Phone', 'text/plain')})
        self.assertIn('Give the phone a name', response.text)
        self.assertFalse(self.env['product.template'].search([('name', 'like', 'Bad Price')]))
        self.assertEqual(self.url_open('/my/retailer').status_code, 200)

    def test_listing_errors_are_fixed_messages(self):
        self.authenticate(self.vendor_user.login, self.vendor_user.login)
        spoof = 'Your payouts are frozen, call 9800000000'
        page = self.url_open(f'/my/retailer/listing/{self.phone_tmpl.id}?error={spoof}')
        self.assertEqual(page.status_code, 200)
        self.assertNotIn(spoof, page.text)
        self.assertNotIn('alert-danger', page.text)

        token = re.search(r'name="csrf_token" value="([^"]+)"', page.text).group(1)
        # Already published: submitting fails and the page explains why.
        response = self.url_open(f'/my/retailer/listing/{self.phone_tmpl.id}/submit', data={'csrf_token': token})
        self.assertIn('error=not_draft', response.url)
        self.assertIn('Only draft listings can be submitted for review.', response.text)

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
