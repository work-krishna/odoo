# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import _, http
from odoo.exceptions import ValidationError
from odoo.http import request

from odoo.addons.pos_online_payment.controllers.payment_portal import PaymentPortal


class PosFonepayPortal(PaymentPortal):
    """ Let Point of Sale fetch Fonepay's own QR code directly, instead of going through the
    generic online-payment flow of showing a link-QR that the customer has to open on their own
    phone before the real (Fonepay) QR code is even requested.

    This reuses `pos_online_payment`'s own transaction-creation route (`pos_order_pay_transaction`)
    so that reference generation, access checks, and linking the transaction to the POS order all
    go through the exact same, already-tested code path as the standard flow. The only difference
    is that the QR code is requested and returned synchronously, in one call, instead of behind an
    intermediate page that the customer's phone would have to load.
    """

    @http.route('/pos/pay/fonepay/qr/<int:pos_order_id>', type='jsonrpc', auth='public')
    def pos_order_pay_fonepay_qr(self, pos_order_id, access_token=None):
        """ Create a Fonepay payment transaction for a POS order and return its QR code.

        :param int pos_order_id: The POS order to pay, as a `pos.order` id.
        :param str access_token: The access token used to verify the request.
        :return: A dict with the transaction `reference` and the base64 `qr_code` image to show.
        :rtype: dict
        :raise ValidationError: If this order isn't set up to be paid through Fonepay, or if
                                 Fonepay itself did not return a QR code.
        """
        pos_order_sudo = self._check_order_access(pos_order_id, access_token)
        self._ensure_session_open(pos_order_sudo)

        user_sudo = request.env.user
        if not pos_order_sudo.partner_id:
            user_sudo = pos_order_sudo.company_id._get_public_user()
        partner_sudo = pos_order_sudo.partner_id or self._get_partner_sudo(user_sudo)
        if not partner_sudo:
            raise ValidationError(_("No partner could be found to pay this order."))

        currency_id = pos_order_sudo.currency_id
        amount_to_pay = self._get_amount_to_pay(pos_order_sudo)
        if not self._is_valid_amount(amount_to_pay, currency_id):
            raise ValidationError(_("There is nothing left to pay for this order."))

        providers_sudo = self._get_allowed_providers_sudo(pos_order_sudo, partner_sudo.id, amount_to_pay)
        fonepay_provider_sudo = providers_sudo.filtered(lambda p: p.code == 'fonepay')[:1]
        if not fonepay_provider_sudo:
            raise ValidationError(_("Fonepay is not available to pay this order."))

        fonepay_pm_sudo = request.env['payment.method'].sudo()._get_compatible_payment_methods(
            fonepay_provider_sudo.ids, partner_sudo.id, currency_id=currency_id.id,
        ).filtered(lambda m: m.code == 'fonepay')[:1]
        if not fonepay_pm_sudo:
            raise ValidationError(_("The Fonepay payment method is not available to pay this order."))

        # Reuse the standard POS online-payment transaction route: it already handles reference
        # generation, linking the transaction to the POS order (`custom_create_values` isn't
        # needed here since `pos_order_pay_transaction` sets it from the URL's `pos_order_id`),
        # and everything else the generic `payment` module expects. This also triggers our
        # `_get_specific_rendering_values` override, which is what actually requests the QR code
        # from Fonepay.
        processing_values = self.pos_order_pay_transaction(
            pos_order_id,
            access_token=access_token,
            provider_id=fonepay_provider_sudo.id,
            payment_method_id=fonepay_pm_sudo.id,
            token_id=None,
            amount=amount_to_pay,
            flow='redirect',
            tokenization_requested=False,
            is_validation=False,
            landing_route=self._get_landing_route(pos_order_id, access_token),
        )
        if processing_values.get('state') == 'error':
            raise ValidationError(
                processing_values.get('state_message')
                or _("Fonepay could not generate a QR code for this order.")
            )

        tx_sudo = request.env['payment.transaction'].sudo().search([
            ('reference', '=', processing_values['reference']),
            ('provider_code', '=', 'fonepay'),
        ], limit=1)
        qr_code = tx_sudo and tx_sudo._fonepay_get_qr_code()
        if not qr_code:
            raise ValidationError(_("Fonepay did not return a QR code for this order."))

        return {
            'reference': tx_sudo.reference,
            'qr_code': qr_code,
        }
