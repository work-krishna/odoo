# -*- coding: utf-8 -*-
from odoo import fields, http
from odoo.exceptions import UserError, ValidationError
from odoo.http import request

from odoo.addons.emi_storefront.controllers.common import (
    UploadError, get_phone, phone_url, read_upload, text, to_float, to_int,
)

KYC_TEXT_FIELDS = (
    'full_name', 'gender', 'date_of_birth', 'phone', 'email', 'citizenship_no', 'citizenship_issue_district',
    'citizenship_issue_date', 'pan_no', 'permanent_address', 'temporary_address', 'occupation', 'employer_name',
    'bank_name', 'bank_account_no', 'guarantor_name', 'guarantor_phone', 'guarantor_relation',
)
KYC_REQUIRED = (
    'full_name', 'date_of_birth', 'phone', 'citizenship_no', 'permanent_address', 'occupation',
    'guarantor_name', 'guarantor_phone', 'guarantor_relation',
)
# (field, label, required)
KYC_DOCUMENTS = (
    ('citizenship_front', 'front of your citizenship', True),
    ('citizenship_back', 'back of your citizenship', True),
    ('photo', 'passport-size photo', True),
    ('income_proof', 'proof of income', True),
    ('nid_front', 'front of your national ID card', False),
    ('nid_back', 'back of your national ID card', False),
    ('guarantor_citizenship_front', "front of your guarantor's citizenship", True),
    ('guarantor_citizenship_back', "back of your guarantor's citizenship", True),
    ('guarantor_nid_front', "front of your guarantor's national ID card", False),
    ('guarantor_nid_back', "back of your guarantor's national ID card", False),
    ('guarantor_photo', "guarantor's passport-size photo", True),
)
# Uploaded on the application itself (field, label, required).
SIGNED_FORMS = (
    ('application_form', 'signed EMI application form', True),
    ('consent_form', 'consent form', False),
)
GENDERS = {'male', 'female', 'other'}
OCCUPATIONS = {'salaried', 'self_employed', 'business', 'other'}


class EmiApply(http.Controller):

    def _form_context(self, phone, values=None, error=None):
        partner = request.env.user.partner_id
        values = dict(values or {})
        values.setdefault('full_name', partner.name)
        values.setdefault('phone', partner.phone)
        values.setdefault('email', partner.email)
        rows = []
        for finance, plan, rate in phone._emi_active_offers():
            rows.append({'finance': finance, 'plan': plan, 'rate': rate})
        return {
            'phone': phone, 'phone_url': phone_url(phone), 'values': values, 'error': error,
            'variants': phone.product_variant_ids, 'offers': rows,
            'options': phone.sudo().downpayment_option_ids.filtered('active'),
            'currency': request.env['res.company']._emi_get_marketplace_company().currency_id,
        }

    @http.route('/phones/<string:phone_slug>/apply', type='http', auth='user', website=True, methods=['GET'])
    def apply_form(self, phone_slug, **kwargs):
        phone = get_phone(phone_slug)
        return request.render('emi_storefront.apply', self._form_context(phone, kwargs))

    @http.route('/phones/<string:phone_slug>/apply', type='http', auth='user', website=True, methods=['POST'])
    def apply_submit(self, phone_slug, **post):
        # The route argument must not be called 'phone': the form has a 'phone' field.
        phone = get_phone(phone_slug)
        try:
            with request.env.cr.savepoint():
                app = self._create_application(phone, post)
                app.action_submit()
        except (UploadError, UserError, ValidationError) as error:
            values = {k: v for k, v in post.items() if isinstance(v, str)}
            return request.render('emi_storefront.apply', self._form_context(phone, values, error=str(error)))
        customer_group = request.env.ref('emi_application.group_emi_customer_portal').sudo()
        if request.env.user.share and request.env.user not in customer_group.user_ids:
            customer_group.write({'user_ids': [(4, request.env.user.id)]})
        return request.redirect(f'{app.access_url}?access_token={app._portal_ensure_token()}&submitted=1')

    def _create_application(self, phone, post):
        """Validate the form and create the application (as superuser, with
        only the fields the customer may set)."""
        variant = phone.product_variant_ids.filtered(lambda v: v.id == to_int(post.get('variant_id')))
        if not variant:
            raise UserError("Choose which version of the phone you want.")
        offers = {(f.id, p.id): (f, p) for f, p, _rate in phone._emi_active_offers()}
        chosen = offers.get((to_int(post.get('finance_company_id')), to_int(post.get('tenure_plan_id'))))
        if not chosen:
            raise UserError("Choose a finance company and a tenure it offers.")
        finance, plan = chosen
        option = phone.sudo().downpayment_option_ids.filtered(
            lambda o: o.active and o.id == to_int(post.get('downpayment_option_id'))
        )

        down_payment = to_float(post.get('down_payment_amount'), None)
        if down_payment is None:
            raise UserError("Enter the down payment you will pay.")

        kyc = {}
        for name in KYC_TEXT_FIELDS:
            value = text(post, name)
            if value:
                kyc[name] = value
        missing = [name.replace('_', ' ') for name in KYC_REQUIRED if not kyc.get(name)]
        if missing:
            raise UserError(f"Please fill in: {', '.join(missing)}.")
        for date_field in ('date_of_birth', 'citizenship_issue_date'):
            if kyc.get(date_field):
                try:
                    kyc[date_field] = fields.Date.to_date(kyc[date_field])
                except ValueError:
                    raise UserError(f"Enter the {date_field.replace('_', ' ')} as a valid date.")
        if kyc.get('gender') and kyc['gender'] not in GENDERS:
            raise UserError("Choose a valid gender.")
        if kyc['occupation'] not in OCCUPATIONS:
            raise UserError("Choose a valid occupation.")
        income = to_float(post.get('monthly_income'))
        if income <= 0:
            raise UserError("Enter your monthly income.")
        kyc['monthly_income'] = income
        for field, label, required in KYC_DOCUMENTS:
            upload = request.httprequest.files.get(field)
            data = read_upload(upload, label, required=required)
            if data:
                kyc[field] = data
                kyc[f'{field}_filename'] = upload.filename
        forms = {}
        for field, label, required in SIGNED_FORMS:
            upload = request.httprequest.files.get(field)
            data = read_upload(upload, label, required=required)
            if data:
                forms.update({field: data, f'{field}_filename': upload.filename})
        if post.get('consent') != 'on':
            raise UserError("Please confirm your details and agree to their verification.")
        kyc['consent_date'] = fields.Datetime.now()

        partner = request.env.user.partner_id
        delivery_street = text(post, 'delivery_street')
        delivery_vals = {}
        if delivery_street:
            delivery_vals['delivery_address_id'] = request.env['res.partner'].sudo().create({
                'type': 'delivery', 'parent_id': partner.commercial_partner_id.id,
                'name': kyc['full_name'], 'street': delivery_street,
                'city': text(post, 'delivery_city'),
                'phone': text(post, 'delivery_phone') or kyc['phone'],
            }).id
        note = text(post, 'delivery_note')
        if note:
            delivery_vals['delivery_note'] = note
        return request.env['emi.application'].sudo().create({
            'partner_id': partner.id,
            'product_id': variant.id,
            'finance_company_id': finance.id,
            'tenure_plan_id': plan.id,
            'downpayment_option_id': option.id or False,
            'down_payment_amount': down_payment,
            'kyc_ids': [(0, 0, kyc)],
            **forms,
            **delivery_vals,
        })
