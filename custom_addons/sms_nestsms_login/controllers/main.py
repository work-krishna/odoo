# Part of Odoo. See LICENSE file for full copyright and licensing details.

from werkzeug.exceptions import NotFound

from odoo import _, http
from odoo.exceptions import AccessDenied
from odoo.http import request

from odoo.addons.sms_nestsms.tools.sms_api import nepal_mobile
from odoo.addons.sms_nestsms_login.models.res_users import CREDENTIAL_TYPE
from odoo.addons.web.controllers.home import Home, ensure_db

SESSION_KEY = 'sms_login_number'


class SmsLogin(Home):

    @http.route()
    def web_login(self, *args, **kw):
        response = super().web_login(*args, **kw)
        if response.is_qweb:
            response.qcontext['sms_login_enabled'] = request.env.company._sms_otp_enabled('login')
        return response

    @http.route('/web/login/sms', type='http', auth='public', website=True, sitemap=False, methods=['GET', 'POST'])
    def web_login_sms(self, phone=None, code=None, redirect=None, restart=None, **kw):
        ensure_db()
        if not request.env.company._sms_otp_enabled('login'):
            raise NotFound()
        if request.session.uid:
            return request.redirect(self._login_redirect(request.session.uid, redirect=redirect))

        values = {'redirect': redirect}
        number = request.session.get(SESSION_KEY)
        if request.httprequest.method == 'POST':
            if restart:
                request.session.pop(SESSION_KEY, None)
                number = None
            elif code is not None and number:
                Users = request.env['res.users']
                user = Users._sms_login_user(number)
                try:
                    if not user:
                        raise AccessDenied(_("That code is not right."))
                    auth_info = request.session.authenticate(request.env, {
                        'type': CREDENTIAL_TYPE, 'login': user.login, 'number': number, 'code': code,
                    })
                except AccessDenied as error:
                    message = error.args[0] if error.args else ''
                    values['error'] = message if message and message != 'Access Denied' else _("That code is not right.")
                else:
                    request.session.pop(SESSION_KEY, None)
                    return request.redirect(self._login_redirect(auth_info['uid'], redirect=redirect))
            elif phone is not None:
                mobile = nepal_mobile(phone)
                if not mobile:
                    values['error'] = _("Enter a Nepali mobile number (98XXXXXXXX).")
                else:
                    # Same answer whether or not the number has an account, so the page
                    # can't be used to find out who is a customer.
                    if request.env['res.users']._sms_login_user(mobile):
                        _otp, error = request.env['sms.nestsms.otp']._nestsms_send('login', mobile, request.env.company)
                        values['error'] = error
                    if not values.get('error'):
                        request.session[SESSION_KEY] = number = mobile
                        values['message'] = _("If this number belongs to an account, we have texted it a code.")
        values.update(
            step='code' if number else 'phone',
            number=number,
            sent_to=number and f"{number[:3]}*****{number[-2:]}",
        )
        response = request.render('sms_nestsms_login.login_sms', values)
        response.headers['Cache-Control'] = 'no-cache'
        return response
