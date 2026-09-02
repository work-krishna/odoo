# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models

from odoo.addons.payment_fonepay import const


class PaymentProvider(models.Model):
    _inherit = 'payment.provider'

    code = fields.Selection(
        selection_add=[('fonepay', "Fonepay")], ondelete={'fonepay': 'set default'}
    )
    fonepay_merchant_code = fields.Char(
        string="Fonepay Merchant Code",
        help="The merchant code assigned to you by Fonepay.",
        required_if_provider='fonepay',
        groups='base.group_system',
    )
    fonepay_username = fields.Char(
        string="Fonepay Username",
        help="The API username provided by Fonepay.",
        required_if_provider='fonepay',
        groups='base.group_system',
    )
    fonepay_password = fields.Char(
        string="Fonepay Password",
        help="The API password provided by Fonepay.",
        required_if_provider='fonepay',
        groups='base.group_system',
    )
    fonepay_secret_key = fields.Char(
        string="Fonepay Secret Key",
        help="Used to sign the requests sent to Fonepay. Found on your merchant profile page "
             "after logging into the Fonepay merchant portal.",
        required_if_provider='fonepay',
        groups='base.group_system',
    )

    # === COMPUTE METHODS === #

    def _get_supported_currencies(self):
        """ Override of `payment` to return the supported currencies. """
        supported_currencies = super()._get_supported_currencies()
        if self.code == 'fonepay':
            supported_currencies = supported_currencies.filtered(
                lambda c: c.name in const.SUPPORTED_CURRENCIES
            )
        return supported_currencies

    # === CRUD METHODS === #

    def _get_default_payment_method_codes(self):
        """ Override of `payment` to return the default payment method codes. """
        self.ensure_one()
        if self.code != 'fonepay':
            return super()._get_default_payment_method_codes()
        return const.DEFAULT_PAYMENT_METHOD_CODES

    # === REQUEST HELPERS === #

    def _build_request_url(self, endpoint, **kwargs):
        """ Override of `payment` to build the request URL. """
        if self.code != 'fonepay':
            return super()._build_request_url(endpoint, **kwargs)
        base_url = const.API_URLS['enabled' if self.state == 'enabled' else 'test']
        print(f"fonepay-url => {base_url}{endpoint}")
        return f'{base_url}{endpoint}'

    def _parse_response_error(self, response):
        """ Override of `payment` to parse the error message. """
        print(f"fonepay-response:: {response}")
        
        if self.code != 'fonepay':
            return super()._parse_response_error(response)
        try:
            return response.json().get('message') or response.text
        except ValueError:
            return response.text
