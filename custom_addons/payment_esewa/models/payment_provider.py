# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import _, fields, models
from odoo.exceptions import ValidationError

from odoo.addons.payment_esewa import const


class PaymentProvider(models.Model):
    _inherit = 'payment.provider'

    code = fields.Selection(selection_add=[('esewa', "eSewa")], ondelete={'esewa': 'set default'})
    esewa_product_code = fields.Char(
        string="eSewa Product Code",
        help="Merchant (product) code given by eSewa. The public test merchant is EPAYTEST.",
        required_if_provider='esewa',
        groups='base.group_system',
        copy=False,
    )
    esewa_secret_key = fields.Char(
        string="eSewa Secret Key",
        help="Secret key used to sign the ePay v2 requests and verify eSewa's responses.",
        required_if_provider='esewa',
        groups='base.group_system',
        copy=False,
    )

    # === COMPUTE METHODS === #

    def _get_supported_currencies(self):
        """ Override of `payment` to return the supported currencies. """
        supported_currencies = super()._get_supported_currencies()
        if self.code == 'esewa':
            supported_currencies = supported_currencies.filtered(
                lambda c: c.name in const.SUPPORTED_CURRENCIES
            )
        return supported_currencies

    # === CRUD METHODS === #

    def _get_default_payment_method_codes(self):
        """ Override of `payment` to return the default payment method codes. """
        self.ensure_one()
        if self.code != 'esewa':
            return super()._get_default_payment_method_codes()
        return const.DEFAULT_PAYMENT_METHOD_CODES

    # === BUSINESS METHODS === #

    def _esewa_environment(self):
        """ 'enabled' (production) or 'test' (eSewa's UAT); a disabled provider is never used. """
        self.ensure_one()
        if self.state == 'disabled':
            raise ValidationError(_("The eSewa payment provider %s is disabled.", self.name))
        return self.state

    def _esewa_get_form_url(self):
        self.ensure_one()
        return const.FORM_URLS[self._esewa_environment()]

    def _build_request_url(self, endpoint, **kwargs):
        """ Override of `payment` to build the status API URL. """
        if self.code != 'esewa':
            return super()._build_request_url(endpoint, **kwargs)
        return const.STATUS_URLS[self._esewa_environment()]
