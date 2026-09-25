# -*- coding: utf-8 -*-
from odoo import http
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.http import request

from odoo.addons.emi_storefront.controllers.common import (
    IMAGE_MIMETYPES, UploadError, current_vendor, read_upload, text, to_float, to_int,
)
from odoo.addons.portal.controllers.portal import CustomerPortal

LISTING_EDITABLE_STATES = ('draft', 'rejected')
# Codes, not messages, go through the URL so a link cannot put its own text on the page.
LISTING_ERRORS = {
    'vendor_not_approved': "Your retailer account must be approved before you can submit listings.",
    'not_draft': "Only draft listings can be submitted for review.",
    'submit_failed': "This listing could not be submitted for review.",
}


class EmiRetailer(http.Controller):

    # ------------------------------------------------------------------
    # Self-registration
    # ------------------------------------------------------------------

    @http.route('/retailer/register', type='http', auth='user', website=True, methods=['GET', 'POST'])
    def retailer_register(self, **post):
        if current_vendor():
            return request.redirect('/my/retailer')
        user = request.env.user
        if current_vendor(include_archived=True):
            return request.render('emi_storefront.retailer_register', {
                'error': "Your retailer account has been closed. Please contact the marketplace to reopen it.",
                'values': {}, 'blocked': True,
            })
        if not user.share:
            return request.render('emi_storefront.retailer_register', {
                'error': "Staff accounts cannot register as retailers; sign in with a customer account.",
                'values': {}, 'blocked': True,
            })
        if request.httprequest.method != 'POST':
            return request.render('emi_storefront.retailer_register', {'values': {}, 'error': None})
        try:
            with request.env.cr.savepoint():
                self._register_vendor(user, post)
        except (UploadError, UserError, ValidationError) as error:
            values = {k: v for k, v in post.items() if isinstance(v, str)}
            return request.render('emi_storefront.retailer_register', {'values': values, 'error': str(error)})
        return request.redirect('/my/retailer?registered=1')

    def _register_vendor(self, user, post):
        values = {key: text(post, key) for key in (
            'business_name', 'pan', 'email', 'phone', 'street', 'city', 'bank_name', 'account_number',
            'account_holder',
        )}
        missing = [k.replace('_', ' ') for k in ('business_name', 'pan', 'phone', 'street', 'account_number')
                   if not values[k]]
        if missing:
            raise UserError(f"Please fill in: {', '.join(missing)}.")
        documents = [f for f in request.httprequest.files.getlist('documents') if f and f.filename]
        if not documents:
            raise UserError("Upload your business registration and PAN/VAT certificates.")
        Partner = request.env['res.partner'].sudo()
        company = Partner.create({
            'name': values['business_name'], 'is_company': True, 'vat': values['pan'],
            'email': values['email'] or user.email, 'phone': values['phone'],
            'street': values['street'], 'city': values['city'],
        })
        bank = False
        if values['bank_name']:
            bank = request.env['res.bank'].sudo().search([('name', '=ilike', values['bank_name'])], limit=1) \
                or request.env['res.bank'].sudo().create({'name': values['bank_name']})
        bank_account = request.env['res.partner.bank'].sudo().create({
            'acc_number': values['account_number'], 'partner_id': company.id,
            'bank_id': bank.id if bank else False,
            'acc_holder_name': values['account_holder'] or values['business_name'],
        })
        vendor = request.env['emi.vendor'].sudo().create({
            'partner_id': company.id,
            'settlement_bank_account_id': bank_account.id,
            'user_ids': [(6, 0, user.ids)],
        })
        attachments = request.env['ir.attachment'].sudo()
        for index, upload in enumerate(documents, start=1):
            attachments |= attachments.create({
                'name': upload.filename, 'datas': read_upload(upload, f'document {index}'),
                'res_model': 'emi.vendor', 'res_id': vendor.id,
            })
        vendor.onboarding_document_ids = [(6, 0, attachments.ids)]
        vendor.action_submit()
        return vendor

    # ------------------------------------------------------------------
    # Dashboard
    # ------------------------------------------------------------------

    def _vendor_or_redirect(self):
        vendor = current_vendor()
        return vendor, (None if vendor else request.redirect('/retailer/register'))

    @http.route('/my/retailer', type='http', auth='user', website=True)
    def retailer_dashboard(self, **kwargs):
        vendor, redirect = self._vendor_or_redirect()
        if redirect:
            return redirect
        listings = request.env['product.template'].sudo().with_context(active_test=False).search(
            [('vendor_id', '=', vendor.id)], order='write_date desc')
        applications = request.env['emi.application'].sudo().search(
            [('vendor_id', '=', vendor.id), ('state', '!=', 'draft')], order='create_date desc', limit=100)
        settlements = request.env['emi.vendor.settlement'].sudo().search(
            [('vendor_id', '=', vendor.id), ('state', '=', 'posted')], order='date desc', limit=50)
        return request.render('emi_storefront.retailer_dashboard', {
            'vendor': vendor, 'listings': listings, 'applications': applications, 'settlements': settlements,
            'registered': kwargs.get('registered'), 'page_name': 'retailer',
            'currency': request.env['res.company']._emi_get_marketplace_company().currency_id,
            'delivery_states': ('disbursed', 'active', 'closed'),
        })

    def _listing(self, vendor, listing_id):
        listing = request.env['product.template'].sudo().browse(listing_id).exists()
        if not listing or listing.vendor_id != vendor:
            raise AccessError("This listing belongs to another retailer.")
        return listing

    @http.route(['/my/retailer/listing/new', '/my/retailer/listing/<int:listing_id>'], type='http', auth='user',
                website=True, methods=['GET', 'POST'])
    def retailer_listing(self, listing_id=None, **post):
        vendor, redirect = self._vendor_or_redirect()
        if redirect:
            return redirect
        listing = self._listing(vendor, listing_id) if listing_id else request.env['product.template']
        editable = not listing or listing.listing_state in LISTING_EDITABLE_STATES
        context = {
            'vendor': vendor, 'listing': listing, 'editable': editable, 'error': LISTING_ERRORS.get(post.get('error')),
            'saved': post.get('saved'),
            'brands': request.env['emi.phone.brand'].sudo().search([]),
            'values': {
                'name': listing.name or '', 'list_price': listing.list_price or '',
                'brand_id': listing.emi_brand_id.id, 'description': listing.description_sale or '',
            },
        }
        if request.httprequest.method != 'POST':
            return request.render('emi_storefront.retailer_listing', context)
        if not editable:
            context['error'] = "Published or pending listings can no longer be edited; ask the marketplace to unpublish it."
            return request.render('emi_storefront.retailer_listing', context)
        try:
            with request.env.cr.savepoint():
                listing = self._save_listing(vendor, listing, post)
        except (UploadError, UserError, ValidationError) as error:
            context['values'] = {k: v for k, v in post.items() if isinstance(v, str)}
            context['error'] = str(error)
            return request.render('emi_storefront.retailer_listing', context)
        return request.redirect(f'/my/retailer/listing/{listing.id}?saved=1')

    def _save_listing(self, vendor, listing, post):
        name = text(post, 'name')
        price = to_float(post.get('list_price'))
        if not name:
            raise UserError("Give the phone a name.")
        if price <= 0:
            raise UserError("Enter the phone's price (VAT included).")
        brand = request.env['emi.phone.brand'].sudo().browse(to_int(post.get('brand_id')) or 0).exists()
        vals = {
            'name': name, 'list_price': price, 'emi_brand_id': brand.id or False,
            'description_sale': text(post, 'description'),
        }
        image = read_upload(request.httprequest.files.get('image'), 'phone photo',
                            allowed=IMAGE_MIMETYPES, required=False)
        if image:
            vals['image_1920'] = image
        if listing:
            listing.write(vals)
            if listing.listing_state == 'rejected':
                listing.action_reset_listing_draft()
            return listing
        # Forced: the listing belongs to this retailer and starts as a draft.
        return request.env['product.template'].sudo().create(dict(vals, vendor_id=vendor.id, sale_ok=True))

    @http.route('/my/retailer/listing/<int:listing_id>/submit', type='http', auth='user', website=True,
                methods=['POST'])
    def retailer_listing_submit(self, listing_id, **post):
        vendor, redirect = self._vendor_or_redirect()
        if redirect:
            return redirect
        listing = self._listing(vendor, listing_id)
        try:
            # As the retailer's own user: action_submit_listing checks membership itself.
            listing.with_user(request.env.user).action_submit_listing()
        except (UserError, AccessError):
            code = ('vendor_not_approved' if vendor.state != 'approved'
                    else 'not_draft' if listing.listing_state != 'draft' else 'submit_failed')
            return request.redirect(f'/my/retailer/listing/{listing.id}?error={code}')
        return request.redirect('/my/retailer')


class EmiRetailerPortal(CustomerPortal):

    def _prepare_home_portal_values(self, counters):
        values = super()._prepare_home_portal_values(counters)
        if 'retailer_count' in counters:
            values['retailer_count'] = 1 if current_vendor() else 0
        return values
