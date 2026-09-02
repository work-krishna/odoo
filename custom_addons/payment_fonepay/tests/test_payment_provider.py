# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo.tests import tagged

from odoo.addons.payment_fonepay import const
from odoo.addons.payment_fonepay.tests.common import FonepayCommon


@tagged('post_install', '-at_install')
class TestPaymentProvider(FonepayCommon):

    def test_incompatible_with_unsupported_currencies(self):
        """ Test that Fonepay is filtered out from compatible providers when the currency is not
        supported. """
        compatible_providers = self.env['payment.provider']._get_compatible_providers(
            self.company_id, self.partner.id, self.amount, currency_id=self.env.ref('base.EUR').id
        )
        self.assertNotIn(self.fonepay, compatible_providers)

    def test_compatible_with_npr(self):
        """ Test that Fonepay is proposed as a compatible provider for NPR payments. """
        compatible_providers = self.env['payment.provider']._get_compatible_providers(
            self.company_id, self.partner.id, self.amount, currency_id=self.currency.id
        )
        self.assertIn(self.fonepay, compatible_providers)

    def test_build_request_url_switches_on_state(self):
        """ Test that the API host used depends on whether the provider is live or in test mode,
        following whatever hosts are configured in `const.API_URLS`. """
        self.fonepay.state = 'test'
        self.assertEqual(
            self.fonepay._build_request_url('/foo'), f"{const.API_URLS['test']}/foo"
        )

        self.fonepay.state = 'enabled'
        self.assertEqual(
            self.fonepay._build_request_url('/foo'), f"{const.API_URLS['enabled']}/foo"
        )
