# -*- coding: utf-8 -*-
from werkzeug.urls import url_encode

from odoo import models

from odoo.addons.payment import utils as payment_utils

PAYMENT_KINDS = ('down_payment', 'installment')


class EmiApplication(models.Model):
    _name = 'emi.application'
    _inherit = ['emi.application', 'portal.mixin']

    def _compute_access_url(self):
        super()._compute_access_url()
        for app in self:
            app.access_url = f'/my/emi/{app.id}'

    def _emi_payment_link(self, kind):
        """Link to the payment form for what is due now, or False."""
        self.ensure_one()
        amount = self._emi_amount_due(kind)
        if kind not in PAYMENT_KINDS or not amount:
            return False
        partner = self.partner_id
        return '/payment/pay?' + url_encode({
            'emi_application_id': self.id,
            'emi_kind': kind,
            'amount': amount,
            'currency_id': self.currency_id.id,
            'partner_id': partner.id,
            'company_id': self._emi_payment_company(kind).id,
            'access_token': payment_utils.generate_access_token(
                partner.id, amount, self.currency_id.id, env=self.env,
            ),
        })

    def _emi_portal_can_access(self, partner):
        self.ensure_one()
        return self.sudo().partner_id.commercial_partner_id == partner.commercial_partner_id

    def _emi_staff_user(self, company):
        """Internal user to follow up an online payment booked in ``company``:
        whoever handled the application for that company, else its creator."""
        self.ensure_one()
        app = self.sudo()
        handler = app.approved_by if company == app.finance_company_id.company_id else app.reviewed_by
        for user in (handler, app.create_uid):
            if user and user.active and not user.share and company in user.company_ids:
                return user
        return self.env.ref('base.user_admin')
