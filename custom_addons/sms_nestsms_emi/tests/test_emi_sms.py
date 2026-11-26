# Part of Odoo. See LICENSE file for full copyright and licensing details.

import re

from odoo.tests import HttpCase, tagged

from odoo.addons.emi_application.tests.common import EmiCommon
from odoo.addons.emi_storefront.tests import test_storefront
from odoo.addons.sms_nestsms.tests.common import TEMPLATE_ID, patch_nestsms


@tagged('post_install', '-at_install')
class TestEmiSms(EmiCommon, HttpCase):

    # The storefront tests' form helpers (their test class itself isn't imported, so its
    # tests don't run twice).
    _apply_data = test_storefront.TestEmiStorefront._apply_data
    _files = test_storefront.TestEmiStorefront._files

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.company.write({
            'sms_nestsms_api_key': 'nsms_live_test',
            'sms_brand_name': 'Flagship-Store',
            'sms_otp_emi': True,
            'sms_otp_emi_template': TEMPLATE_ID,
        })
        cls.slug = cls.env['ir.http']._slug(cls.phone_tmpl)
        cls.apply_url = f'/phones/{cls.slug}/apply'

    def setUp(self):
        super().setUp()
        self.nestsms = patch_nestsms(self)
        login = self.customer_user.login
        self.authenticate(login, login + 'x' * max(0, 8 - len(login)))

    def _csrf(self, url):
        return re.search(r'name="csrf_token" value="([^"]+)"', self.url_open(url).text).group(1)

    def _verify_url(self):
        return f'/my/emi/verify-phone?redirect=/phones/{self.slug}/apply'

    def _verify(self, **data):
        return self.url_open(self._verify_url(), data={'csrf_token': self._csrf(self._verify_url()), **data})

    def _prove(self, number='9841234567'):
        self._verify(send='1', phone=number)
        return self._verify(code=self.nestsms.calls[-1]['payload']['variables']['otp'])

    def test_unproven_applicant_is_sent_to_verify(self):
        response = self.url_open(self.apply_url)
        self.assertIn('/my/emi/verify-phone', response.url)
        self.assertIn('Confirm your mobile number', response.text)

    def test_verify_then_apply(self):
        response = self._verify(send='1', phone='+977 984-1234567')
        self.assertIn('984*****67', response.text)
        [call] = self.nestsms.calls
        self.assertEqual((call['payload']['to'], call['payload']['template_id']), ('9841234567', TEMPLATE_ID))
        code = call['payload']['variables']['otp']
        self.assertIn('4 tries left', self._verify(code='000000' if code != '000000' else '111111').text)
        response = self._verify(code=code)
        self.assertTrue(response.url.endswith(self.apply_url))
        self.assertEqual(self.customer.sms_verified_phone, '9841234567')
        self.assertRegex(response.text, r'name="phone"[^>]*value="9841234567"[^>]*readonly|readonly[^>]*name="phone"')

        # Whatever number the form sends, the application gets the proven one.
        token = self._csrf(self.apply_url)
        response = self.url_open(self.apply_url, data=self._apply_data(token, phone='9800000000'), files=self._files())
        self.assertIn('submitted', response.url)
        app = self.env['emi.application'].search([('partner_id', '=', self.customer.id)])
        self.assertEqual(app.kyc_ids.phone, '9841234567')

    def test_unproven_submission_refused(self):
        token = self._csrf(self._verify_url())
        response = self.url_open(self.apply_url, data=self._apply_data(token), files=self._files())
        self.assertIn('/my/emi/verify-phone', response.url)
        self.assertFalse(self.env['emi.application'].search([('partner_id', '=', self.customer.id)]))

    def test_only_local_redirects(self):
        self.customer.sms_verified_phone = False
        self._verify(send='1', phone='9841234567')
        url = '/my/emi/verify-phone?redirect=//evil.example.com'
        response = self.url_open(url, data={'csrf_token': self._csrf(url), 'code': self.nestsms.calls[-1]['payload']['variables']['otp']})
        self.assertNotIn('evil.example.com', response.url)

    def test_switched_off(self):
        self.env.company.sms_otp_emi = False
        response = self.url_open(self.apply_url)
        self.assertTrue(response.url.endswith(self.apply_url))
        self.assertNotIn('Confirmed by SMS', response.text)
