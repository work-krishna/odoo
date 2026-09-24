# Part of Odoo. See LICENSE file for full copyright and licensing details.

import base64

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.serialization import pkcs12

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from odoo.addons.payment_connectips import const
from odoo.addons.payment_connectips.controllers.main import ConnectipsController


class PaymentProvider(models.Model):
    _inherit = 'payment.provider'

    code = fields.Selection(
        selection_add=[('connectips', "connectIPS")], ondelete={'connectips': 'set default'},
    )
    connectips_merchant_id = fields.Char(
        string="Merchant ID", required_if_provider='connectips', groups='base.group_system',
        help="Numeric merchant ID assigned by NCHL.",
    )
    connectips_app_id = fields.Char(
        string="App ID", required_if_provider='connectips', groups='base.group_system',
        help="Application ID assigned by NCHL, e.g. MER-550-APP-1. Also the API username.",
    )
    connectips_app_name = fields.Char(
        string="App Name", required_if_provider='connectips', groups='base.group_system',
    )
    connectips_password = fields.Char(
        string="API Password", required_if_provider='connectips', groups='base.group_system',
        help="Password for the transaction validation API (basic authentication with the App ID).",
    )
    connectips_certificate = fields.Binary(
        string="Creditor Certificate (.pfx)", attachment=True, groups='base.group_system',
        help="The CREDITOR.pfx file from NCHL used to sign requests.",
    )
    connectips_certificate_password = fields.Char(
        string="Certificate Password", groups='base.group_system',
    )
    connectips_test_base_url = fields.Char(
        string="Test Base URL", default=const.DEFAULT_BASE_URLS['test'], groups='base.group_system',
        help="Base URL of the NCHL UAT environment (some merchants are given a :7443 port).",
    )
    connectips_live_base_url = fields.Char(
        string="Live Base URL", default=const.DEFAULT_BASE_URLS['enabled'], groups='base.group_system',
    )
    connectips_success_url = fields.Char(compute='_compute_connectips_redirect_urls')
    connectips_failure_url = fields.Char(compute='_compute_connectips_redirect_urls')

    @api.depends('code')
    def _compute_connectips_redirect_urls(self):
        for provider in self:
            base_url = provider.get_base_url()
            provider.connectips_success_url = f'{base_url}{ConnectipsController._return_url}'
            provider.connectips_failure_url = f'{base_url}{ConnectipsController._failure_url}'

    def _get_supported_currencies(self):
        """ Override of `payment` to return the supported currencies. """
        supported_currencies = super()._get_supported_currencies()
        if self.code == 'connectips':
            supported_currencies = supported_currencies.filtered(
                lambda c: c.name in const.SUPPORTED_CURRENCIES
            )
        return supported_currencies

    def _get_default_payment_method_codes(self):
        """ Override of `payment` to return the default payment method codes. """
        self.ensure_one()
        if self.code != 'connectips':
            return super()._get_default_payment_method_codes()
        return const.DEFAULT_PAYMENT_METHOD_CODES

    # === BUSINESS METHODS === #

    def _connectips_base_url(self):
        self.ensure_one()
        url = self.connectips_live_base_url if self.state == 'enabled' else self.connectips_test_base_url
        return (url or const.DEFAULT_BASE_URLS['enabled' if self.state == 'enabled' else 'test']).rstrip('/')

    def _build_request_url(self, endpoint, **kwargs):
        """ Override of `payment` to build the request URL. """
        if self.code != 'connectips':
            return super()._build_request_url(endpoint, **kwargs)
        return self._connectips_base_url() + endpoint

    def _build_request_auth(self, **kwargs):
        """ Override of `payment` to use basic authentication with the App ID. """
        if self.code != 'connectips':
            return super()._build_request_auth(**kwargs)
        return (self.connectips_app_id, self.connectips_password)

    def _connectips_sign(self, message):
        """ Base64 SHA256withRSA signature of ``message`` with the creditor certificate. """
        self.ensure_one()
        if not self.connectips_certificate:
            raise ValidationError(_("Upload the connectIPS creditor certificate (.pfx) first."))
        try:
            private_key, _cert, _extra = pkcs12.load_key_and_certificates(
                base64.b64decode(self.connectips_certificate),
                (self.connectips_certificate_password or '').encode() or None,
            )
        except ValueError:
            raise ValidationError(_("The connectIPS certificate could not be opened; check its password."))
        signature = private_key.sign(message.encode(), padding.PKCS1v15(), hashes.SHA256())
        return base64.b64encode(signature).decode()
