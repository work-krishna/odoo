# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request

from odoo.addons.emi_finance.tools import emi_math
from odoo.addons.emi_storefront.controllers.common import get_phone, phone_url, to_float, to_int

SORTS = {
    'price_asc': 'list_price asc, id desc',
    'price_desc': 'list_price desc, id desc',
    'newest': 'create_date desc, id desc',
    'name': 'name asc, id desc',
}


class EmiCatalog(http.Controller):
    _per_page = 24

    @http.route(['/phones', '/phones/page/<int:page>'], type='http', auth='public', website=True, sitemap=True)
    def phones(self, page=1, search='', brand=None, retailer=None, min_price=None, max_price=None,
               order='price_asc', **kwargs):
        Product = request.env['product.template'].sudo()
        base_domain = Product._emi_storefront_domain()
        domain = list(base_domain)
        search = search.strip() if isinstance(search, str) else ''
        if search:
            domain += ['|', ('name', 'ilike', search), ('emi_brand_id.name', 'ilike', search)]
        brand_id, retailer_id = to_int(brand), to_int(retailer)
        if brand_id:
            domain.append(('emi_brand_id', '=', brand_id))
        if retailer_id:
            domain.append(('vendor_id', '=', retailer_id))
        low, high = to_float(min_price, None), to_float(max_price, None)
        if low is not None:
            domain.append(('list_price', '>=', low))
        if high is not None:
            domain.append(('list_price', '<=', high))
        order = order if order in SORTS else 'price_asc'

        url_args = {k: v for k, v in {
            'search': search, 'brand': brand_id, 'retailer': retailer_id,
            'min_price': min_price, 'max_price': max_price, 'order': order,
        }.items() if v}
        total = Product.search_count(domain)
        pager = request.website.pager(url='/phones', total=total, page=page, step=self._per_page, url_args=url_args)
        phones = Product.search(domain, limit=self._per_page, offset=pager['offset'], order=SORTS[order])
        offers = Product._emi_active_offers()
        catalog = Product.search(base_domain)
        return request.render('emi_storefront.catalog', {
            'phones': phones,
            'quotes': {phone.id: phone._emi_best_quote(offers) for phone in phones},
            'phone_url': phone_url,
            'pager': pager,
            'brands': catalog.emi_brand_id.sorted('name'),
            'retailers': catalog.vendor_id.sorted('name'),
            'search': search, 'brand_id': brand_id, 'retailer_id': retailer_id,
            'min_price': min_price or '', 'max_price': max_price or '', 'order': order,
            'currency': request.env['res.company']._emi_get_marketplace_company().currency_id,
        })

    @http.route('/phones/<string:phone_slug>', type='http', auth='public', website=True, sitemap=False)
    def phone_detail(self, phone_slug, variant=None, finance=None, tenure=None, down_payment=None, **kwargs):
        phone = get_phone(phone_slug)
        variants = phone.product_variant_ids
        selected_variant = variants.filtered(lambda v: v.id == to_int(variant))[:1] or variants[:1]
        price = selected_variant.lst_price
        offers = phone._emi_active_offers()
        rows = []
        for finance_company, plan, rate in offers:
            minimum, option = phone._emi_min_down_payment_option(finance_company, price)
            result = emi_math.quote(price - minimum, rate.rate_percent, plan.months, rate.calc_method)
            rows.append({'finance': finance_company, 'plan': plan, 'rate': rate, 'minimum': minimum,
                         'option': option, **result})

        # Calculator: the customer's own choice of lender, tenure and down payment.
        chosen = next((r for r in rows if r['finance'].id == to_int(finance) and r['plan'].id == to_int(tenure)),
                      None)
        calculation, calc_error = None, None
        if chosen:
            amount = to_float(down_payment, chosen['minimum'])
            if amount < chosen['minimum'] - 0.005:
                calc_error = "The down payment is below this lender's minimum."
            elif amount >= price:
                calc_error = "The down payment must be less than the price."
            else:
                calculation = dict(
                    emi_math.quote(price - amount, chosen['rate'].rate_percent, chosen['plan'].months,
                                   chosen['rate'].calc_method),
                    finance=chosen['finance'], plan=chosen['plan'], rate=chosen['rate'], option=chosen['option'],
                    down_payment=amount, principal=price - amount,
                )
        return request.render('emi_storefront.phone_detail', {
            'phone': phone, 'variants': variants, 'variant': selected_variant, 'price': price,
            'rows': sorted(rows, key=lambda r: (r['finance'].name, r['plan'].months)),
            'calculation': calculation, 'calc_error': calc_error,
            'selected_finance': to_int(finance), 'selected_tenure': to_int(tenure),
            'down_payment': down_payment or '',
            'phone_url': phone_url(phone),
            'currency': request.env['res.company']._emi_get_marketplace_company().currency_id,
            'finance_companies': {r['finance'] for r in rows},
        })
