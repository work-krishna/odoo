# -*- coding: utf-8 -*-
from odoo import api, models

from odoo.addons.emi_finance.tools import emi_math

IMAGE_FIELDS = ('image_1920', 'image_1024', 'image_512', 'image_256', 'image_128')


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    @api.model
    def _emi_storefront_domain(self):
        """Phones customers may see and apply for."""
        return [
            ('active', '=', True),
            ('listing_state', '=', 'published'),
            ('vendor_id.state', '=', 'approved'),
            ('vendor_id.active', '=', True),
            ('sale_ok', '=', True),
        ]

    def _emi_is_on_storefront(self):
        self.ensure_one()
        return bool(self.sudo().filtered_domain(self._emi_storefront_domain()))

    def _can_return_content(self, field_name=None, access_token=None):
        # Visitors have no read access to products (no website_sale), so
        # /web/image would serve the placeholder for storefront phones.
        if field_name in IMAGE_FIELDS and self._emi_is_on_storefront():
            return True
        return super()._can_return_content(field_name, access_token)

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
        return self._emi_min_down_payment_option(finance, price)[0]

    def _emi_min_down_payment_option(self, finance, price):
        """(smallest down payment, the down payment option allowing it); the
        option is empty when the phone has none and the lender's default applies."""
        self.ensure_one()
        options = self.sudo().downpayment_option_ids.filtered('active')
        if options:
            option = min(options, key=lambda o: (o.compute_min_amount(price), not o.is_default))
            return option.compute_min_amount(price), option
        return price * finance.min_down_payment_percent / 100.0, options

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


class ProductProduct(models.Model):
    _inherit = 'product.product'

    def _can_return_content(self, field_name=None, access_token=None):
        variant = self.sudo()
        if field_name in IMAGE_FIELDS and variant.active and variant.product_tmpl_id._emi_is_on_storefront():
            return True
        return super()._can_return_content(field_name, access_token)
