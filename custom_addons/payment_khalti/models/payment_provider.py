# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import _, fields, models
from odoo.exceptions import ValidationError

from odoo.addons.payment_khalti import const


class PaymentProvider(models.Model):
    _inherit = 'payment.provider'

    code = fields.Selection(selection_add=[('khalti', "Khalti")], ondelete={'khalti': 'set default'})
    khalti_secret_key = fields.Char(
        string="Khalti Secret Key",
        help="The live_secret_key from the Khalti merchant dashboard (test-admin.khalti.com "
             "for the sandbox, admin.khalti.com for production).",
        required_if_provider='khalti',
        groups='base.group_system',
    )

    def _get_supported_currencies(self):
        """ Override of `payment` to return the supported currencies. """
        supported_currencies = super()._get_supported_currencies()
        if self.code == 'khalti':
            supported_currencies = supported_currencies.filtered(
                lambda c: c.name in const.SUPPORTED_CURRENCIES
            )
        return supported_currencies

    def _get_default_payment_method_codes(self):
        """ Override of `payment` to return the default payment method codes. """
        self.ensure_one()
        if self.code != 'khalti':
            return super()._get_default_payment_method_codes()
        return const.DEFAULT_PAYMENT_METHOD_CODES

    def _build_request_url(self, endpoint, **kwargs):
        """ Override of `payment` to build the request URL. """
        if self.code != 'khalti':
            return super()._build_request_url(endpoint, **kwargs)
        if self.state == 'disabled':  # Never the sandbox by default: a disabled provider is not used.
            raise ValidationError(_("The Khalti payment provider %s is disabled.", self.name))
        return const.API_URLS[self.state] + endpoint

    def _build_request_headers(self, method, endpoint, payload, **kwargs):
        """ Override of `payment` to authenticate with the secret key. """
        if self.code != 'khalti':
            return super()._build_request_headers(method, endpoint, payload, **kwargs)
        return {'Authorization': f'Key {self.khalti_secret_key}'}

    def _parse_response_error(self, response):
        """ Override of `payment` to surface Khalti's validation messages. """
        if self.code != 'khalti':
            return super()._parse_response_error(response)
        try:
            data = response.json()
        except ValueError:
            return response.text
        if isinstance(data, dict):
            return data.get('detail') or data.get('error_key') or '; '.join(
                f"{key}: {value}" for key, value in data.items()
            )
        return response.text
