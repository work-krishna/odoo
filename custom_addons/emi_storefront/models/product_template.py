# -*- coding: utf-8 -*-
from odoo import api, models

from odoo.addons.emi_finance.tools import emi_math


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    @api.model
    def _emi_storefront_domain(self):
        """Phones customers may see and apply for."""
        return [
            ('listing_state', '=', 'published'),
            ('vendor_id.state', '=', 'approved'),
            ('vendor_id.active', '=', True),
            ('sale_ok', '=', True),
        ]

    def _emi_is_on_storefront(self):
        self.ensure_one()
        return bool(self.sudo().filtered_domain(self._emi_storefront_domain()))

    @api.model
    def _emi_active_offers(self):
        """(finance company, tenure plan, rate) triples customers can choose today."""
        Rate = self.env['emi.interest.rate'].sudo()
        offers = []
        for finance in self.env['emi.finance.company'].sudo().search([]):
            plans = finance.tenure_plan_ids or self.env['emi.tenure.plan'].sudo().search([])
            for plan in plans:
                rate = Rate.get_active_rate(finance.id, plan.id)
                if rate:
                    offers.append((finance, plan, rate))
        return offers

    def _emi_min_down_payment(self, finance, price):
        """Smallest down payment the customer may make for this phone and lender."""
        self.ensure_one()
        options = self.sudo().downpayment_option_ids.filtered('active')
        if options:
            return min(option.compute_min_amount(price) for option in options)
        return price * finance.min_down_payment_percent / 100.0

    def _emi_best_quote(self, offers=None, price=None):
        """Lowest monthly EMI across today's offers, with the minimum down payment."""
        self.ensure_one()
        price = self.list_price if price is None else price
        best = None
        for finance, plan, rate in offers if offers is not None else self._emi_active_offers():
            principal = price - self._emi_min_down_payment(finance, price)
            if principal <= 0:
                continue
            result = emi_math.quote(principal, rate.rate_percent, plan.months, rate.calc_method)
            if best is None or result['emi'] < best['emi']:
                best = dict(result, finance=finance, plan=plan, rate=rate, principal=principal)
        return best
