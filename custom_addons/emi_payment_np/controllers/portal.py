# -*- coding: utf-8 -*-
from werkzeug.exceptions import NotFound

from odoo import _, http
from odoo.exceptions import AccessError, MissingError, ValidationError
from odoo.http import request
from odoo.tools import consteq

from odoo.addons.payment import utils as payment_utils
from odoo.addons.payment.controllers import portal as payment_portal
from odoo.addons.portal.controllers.portal import CustomerPortal
from odoo.addons.emi_payment_np.models.application import PAYMENT_KINDS


def _get_application(app_id, access_token=None):
    """Own application of the logged-in customer, or any application with its access token."""
    app_sudo = request.env['emi.application'].sudo().browse(app_id).exists()
    if not app_sudo:
        raise MissingError(_("This application does not exist."))
    user = request.env.user
    if not user._is_public() and app_sudo._emi_portal_can_access(user.partner_id):
        return app_sudo
    if access_token and app_sudo.access_token and consteq(app_sudo.access_token, access_token):
        return app_sudo
    raise AccessError(_("You cannot access this application."))


class EmiCustomerPortal(CustomerPortal):

    def _emi_domain(self):
        partner = request.env.user.partner_id.commercial_partner_id
        return [('partner_id', 'child_of', partner.id)]

    def _prepare_home_portal_values(self, counters):
        values = super()._prepare_home_portal_values(counters)
        if 'emi_count' in counters:
            values['emi_count'] = request.env['emi.application'].sudo().search_count(self._emi_domain())
        return values

    @http.route('/my/emi', type='http', auth='user', website=True)
    def portal_my_emi(self, **kwargs):
        applications = request.env['emi.application'].sudo().search(self._emi_domain())
        return request.render('emi_payment_np.portal_my_emi', {
            'applications': applications, 'page_name': 'emi',
        })

    @http.route('/my/emi/<int:app_id>', type='http', auth='public', website=True)
    def portal_my_emi_detail(self, app_id, access_token=None, **kwargs):
        try:
            app_sudo = _get_application(app_id, access_token)
        except (AccessError, MissingError):
            return request.redirect('/my')
        return request.render('emi_payment_np.portal_my_emi_detail', {
            'application': app_sudo, 'page_name': 'emi',
            'down_payment_link': app_sudo._emi_payment_link('down_payment'),
            'installment_link': app_sudo._emi_payment_link('installment'),
            'down_payment_due': app_sudo._emi_amount_due('down_payment'),
            'installment_due': app_sudo._emi_amount_due('installment'),
        })


class EmiPaymentPortal(payment_portal.PaymentPortal):

    @http.route()
    def payment_pay(self, *args, amount=None, emi_application_id=None, emi_kind=None, access_token=None, **kwargs):
        """ Override of `payment` to take the amount, partner and company from the EMI application. """
        app_id = self._cast_as_int(emi_application_id)
        if app_id:
            app_sudo = request.env['emi.application'].sudo().browse(app_id).exists()
            if not app_sudo or emi_kind not in PAYMENT_KINDS:
                raise ValidationError(_("The provided parameters are invalid."))
            amount = self._cast_as_float(amount)
            if not payment_utils.check_access_token(
                access_token, app_sudo.partner_id.id, amount, app_sudo.currency_id.id,
            ):
                raise ValidationError(_("The provided parameters are invalid."))
            kwargs.update({
                'reference': app_sudo.name,
                'currency_id': app_sudo.currency_id.id,
                'partner_id': app_sudo.partner_id.id,
                'company_id': app_sudo._emi_payment_company(emi_kind).id,
                'emi_application_id': app_id,
                'emi_kind': emi_kind,
            })
            # The link's token is proven here; the payment page may be shown
            # to another logged-in user, whose own token would not match.
            request.update_context(emi_payment_link_application_id=app_id)
        return super().payment_pay(*args, amount=amount, access_token=access_token, **kwargs)

    def _get_extra_payment_form_values(self, emi_application_id=None, emi_kind=None, access_token=None, **kwargs):
        """ Override of `payment` to route the transaction through the EMI application.

        Core pages (invoices, payment methods) pass their query string here as
        well: the EMI values, which carry the application's portal token, are
        only added once access to that application is proven. """
        form_values = super()._get_extra_payment_form_values(
            emi_application_id=emi_application_id, emi_kind=emi_kind, access_token=access_token, **kwargs
        )
        app_id = self._cast_as_int(emi_application_id)
        if app_id and emi_kind in PAYMENT_KINDS:
            try:
                app_sudo = _get_application(app_id, access_token)
            except (AccessError, MissingError):
                app_sudo = request.env['emi.application'].sudo().browse(app_id).exists()
                if not app_sudo or request.env.context.get('emi_payment_link_application_id') != app_id:
                    return form_values
            form_values.update({
                'amount': app_sudo._emi_amount_due(emi_kind),  # never more than is due now
                'transaction_route': f'/emi/transaction/{app_id}/{emi_kind}',
                'landing_route': f'{app_sudo.access_url}?access_token={app_sudo._portal_ensure_token()}',
                'access_token': app_sudo.access_token,
            })
        return form_values

    @http.route('/emi/transaction/<int:app_id>/<string:kind>', type='jsonrpc', auth='public')
    def emi_transaction(self, app_id, kind, access_token=None, **kwargs):
        """ Create the transaction for what is due now and return its processing values. """
        if kind not in PAYMENT_KINDS:
            raise NotFound()
        try:
            app_sudo = _get_application(app_id, access_token)
        except (AccessError, MissingError):
            raise ValidationError(_("The access token is invalid."))
        amount = app_sudo._emi_amount_due(kind)
        if not amount:
            raise ValidationError(_("Nothing is due on this application right now."))
        self._validate_transaction_kwargs(kwargs)
        self._emi_check_payment_option(app_sudo, kind, amount, kwargs)
        kwargs.update({
            'amount': amount,  # server-side amount, whatever the form posted
            'currency_id': app_sudo.currency_id.id,
            'partner_id': app_sudo.partner_id.id,
            'reference_prefix': app_sudo.name,
        })
        tx_sudo = self._create_transaction(
            custom_create_values={'emi_application_id': app_sudo.id, 'emi_payment_kind': kind},
            **kwargs,
        )
        if tx_sudo.company_id != app_sudo._emi_payment_company(kind):
            raise ValidationError(_("This payment method is not available for this payment."))
        return tx_sudo._get_processing_values()

    def _emi_check_payment_option(self, app_sudo, kind, amount, kwargs):
        """ Only what the payment form offers for this loan: an active,
        published provider of the collecting company (test mode for internal
        users only) and one of its payment methods or the customer's tokens. """
        unavailable = ValidationError(_("This payment method is not available for this payment."))
        if kwargs.get('is_validation'):
            raise unavailable
        company = app_sudo._emi_payment_company(kind)
        partner = app_sudo.partner_id
        providers_sudo = request.env['payment.provider'].sudo()._get_compatible_providers(
            company.id, partner.id, amount, currency_id=app_sudo.currency_id.id,
        )
        if not request.env.user._is_internal():
            providers_sudo = providers_sudo.filtered(lambda p: p.state == 'enabled')
        provider_sudo = providers_sudo.filtered(lambda p: p.id == self._cast_as_int(kwargs.get('provider_id')))
        if not provider_sudo or provider_sudo.company_id != company:
            raise unavailable
        if kwargs.get('flow') == 'token':
            tokens_sudo = request.env['payment.token'].sudo()._get_available_tokens(provider_sudo.ids, partner.id)
            if self._cast_as_int(kwargs.get('token_id')) not in tokens_sudo.ids:
                raise unavailable
        else:
            methods_sudo = request.env['payment.method'].sudo()._get_compatible_payment_methods(
                provider_sudo.ids, partner.id, currency_id=app_sudo.currency_id.id,
            )
            if self._cast_as_int(kwargs.get('payment_method_id')) not in methods_sudo.ids:
                raise unavailable
