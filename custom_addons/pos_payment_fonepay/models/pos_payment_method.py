# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import _, api, models
from odoo.exceptions import UserError, ValidationError


class PosPaymentMethod(models.Model):
    _inherit = 'pos.payment.method'

    def _get_payment_method_type(self):
        """ Override of `point_of_sale` to add Fonepay as a payment method type.

        Fonepay is registered as its own top-level type (like e.g. `pos_cashdro` does for its
        cash machine) rather than through the `terminal`/`use_payment_terminal` sub-selection,
        since there is exactly one way to pay with Fonepay, not several terminal brands to choose
        from.
        """
        return super()._get_payment_method_type() + [('fonepay', "Fonepay")]

    @api.constrains('payment_method_type', 'company_id')
    def _check_fonepay_provider_configured(self):
        for pos_payment_method in self:
            if pos_payment_method.payment_method_type == 'fonepay':
                pos_payment_method._get_fonepay_provider()  # Raises if none is configured.

    def _get_fonepay_provider(self):
        """ Return the enabled Fonepay payment provider for this payment method's company.

        Note: self.ensure_one()

        :return: The Fonepay provider.
        :rtype: payment.provider
        :raise UserError: If no enabled Fonepay provider is configured for the company.
        """
        self.ensure_one()
        provider_sudo = self.env['payment.provider'].sudo().search([
            ('code', '=', 'fonepay'),
            ('company_id', '=', self.company_id.id),
            ('state', '!=', 'disabled'),
        ], limit=1)
        if not provider_sudo:
            raise UserError(_(
                "No enabled Fonepay payment provider is configured for company %s. Configure "
                "one under Payment Providers first.",
                self.company_id.name,
            ))
        return provider_sudo

    def fonepay_request_qr(self, amount, reference):
        """ Create a Fonepay payment transaction for a POS payment and request its QR code.

        Note: self.ensure_one()

        :param float amount: The amount to charge.
        :param str reference: A human-readable label for the transaction (e.g. the POS order
                               name), used to build a unique transaction reference.
        :return: A dict with the transaction `reference` and the base64 `qr_code` image to show.
        :rtype: dict
        :raise UserError: If Fonepay rejects the request or returns no QR code.
        """
        self.ensure_one()
        provider_sudo = self._get_fonepay_provider()

        tx_sudo = self.env['payment.transaction'].sudo().create({
            'provider_id': provider_sudo.id,
            'payment_method_id': self.env.ref('payment_fonepay.payment_method_fonepay').id,
            'reference': self.env['payment.transaction']._compute_reference(
                'fonepay', prefix=f'POS-{reference}',
            ),
            'amount': amount,
            'currency_id': (self.journal_id.currency_id or self.company_id.currency_id).id,
            'partner_id': self.env.user.partner_id.id,
            'operation': 'online_direct',
        })
        try:
            tx_sudo._fonepay_request_qr()
        except ValidationError as error:
            raise UserError(str(error))
        tx_sudo._set_pending()

        return {
            'reference': tx_sudo.reference,
            'qr_code': tx_sudo._fonepay_get_qr_code(),
        }

    def fonepay_check_status(self, reference):
        """ Check the status of a Fonepay POS payment transaction.

        Note: self.ensure_one()

        :param str reference: The transaction reference returned by `fonepay_request_qr`.
        :return: A dict with the transaction's current `state`.
        :rtype: dict
        :raise UserError: If no transaction matches the given reference.
        """
        self.ensure_one()
        tx_sudo = self.env['payment.transaction'].sudo().search([
            ('reference', '=', reference), ('provider_code', '=', 'fonepay'),
        ], limit=1)
        if not tx_sudo:
            raise UserError(_("Unknown Fonepay transaction: %s.", reference))
        tx_sudo._fonepay_check_qr_status()
        return {'state': tx_sudo.state}
