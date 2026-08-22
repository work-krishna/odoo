# -*- coding: utf-8 -*-
import logging
import secrets
from datetime import datetime, timedelta
from odoo import http, SUPERUSER_ID, _
from odoo.http import request
from odoo.addons.web.controllers.utils import ensure_db, _get_login_redirect_url
import re
_logger = logging.getLogger(__name__)


class SGGMOTPController(http.Controller):

    @http.route('/otp-login/send', type='jsonrpc', auth='public', website=True)
    def send_otp(self, email=None, **kw):
        ensure_db()

        if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
            return {'status': 'error', 'message': _('Please enter a valid email address.')}
        if not email:
            return {'status': 'error', 'message': _('Email is required.')}
        otp = ''.join(secrets.choice('0123456789') for _ in range(6))
        request.session['otp_login'] = {
            'email': email,
            'otp': otp,
            'expires_at': (datetime.now() + timedelta(minutes=10)).timestamp(),
        }
        try:
            template = request.env.ref('i8_otp_login.otp_email_template_otp_login', raise_if_not_found=False)
            if template:
                template.sudo().with_context(otp_code=otp).send_mail(
                    request.env.company.partner_id.id,
                    force_send=True,

                    email_values={
                        'email_from': request.env.company.email_formatted,
                        'email_to': email},
                )
            _logger.info("------------------------------------------------")
            _logger.info("OTP FOR %s IS: %s", email, otp)
            _logger.info("------------------------------------------------")
            return {'status': 'success'}
        except Exception as e:
            _logger.error("Mail Error: %s", str(e))
            return {'status': 'success', 'message': 'Mail failed, check console for OTP.'}

    @http.route(['/otp-login/verify', '/donation/verify_otp'], type='jsonrpc', auth='public', website=True)
    def verify_otp(self, code=None, redirect=None, **kw):
        ensure_db()
        otp_data = request.session.get('otp_login')

        if not otp_data or (otp_data.get('otp') != code):
            return {'status': 'error', 'message': _('Invalid OTP code.')}

        try:
            email = otp_data.get('email')
            UserSudo = request.env['res.users'].sudo()
            user = UserSudo.search([('login', '=', email)], limit=1)

            if not user:
                user = UserSudo.create({
                    'name': email.split('@')[0],
                    'login': email,
                    'email': email,
                    'group_ids': [(4, request.env.ref('base.group_portal').id)],
                })
            request.env.cr.commit()
            request.session.uid = user.id
            request.session.login = user.login
            session_token = user._compute_session_token(request.session.sid)
            request.session.session_token = session_token
            request.session.is_dirty = True

            request.update_env(user=user.id)
            request.session.pop('otp_login', None)
            request.env.cr.commit()

            url = request.httprequest.referrer or '/donation'
            final_url = _get_login_redirect_url(user.id, url)
            if '/web/login' in final_url:
                _logger.info("Redirecting from login page to Home Page.")
                final_url = '/'
            return {
                'status': 'success',
                'redirect': final_url
            }
        except Exception as e:
            _logger.exception("Login failed")
            return {'status': 'error', 'message': f"System Error: {str(e)}"}