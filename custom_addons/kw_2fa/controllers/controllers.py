import re
import logging
from odoo import http, _
from odoo.http import request
from odoo.exceptions import AccessDenied, UserError
from odoo.addons.web.controllers import home as web_home

_logger = logging.getLogger(__name__)


class ExtendedHome(web_home.Home):

    def _get_pre_user(self):
        return request.env['res.users'].sudo().browse(
            request.session['pre_uid'])

    def _kw_finalize_session(self):
        request.session.finalize(request.env)
        request.update_env(user=request.session.uid)
        request.update_context(**request.session.context)

    @http.route(route='/kw_2fa/setup_totp', type='http', auth='public',
                website=True)
    def kw_2fa_setup_totp(self, **kw):
        user = self._get_pre_user()
        request.update_context(lang=user.lang)
        issuer = request.httprequest.host.split(':', 1)[0]
        return request.render('kw_2fa.setup_totp', {
            **user._kw_generate_totp_qr_data(issuer), })

    @http.route(route='/kw_2fa/enable_totp', type='http', auth='public',
                methods=['POST'], website=True)
    def kw_2fa_enable_totp(self, totp_secret=None, totp_code=None, **kw):
        user = self._get_pre_user()

        try:
            code = int(re.sub(r'\s', '', totp_code))
        except ValueError:
            raise UserError(_(
                'The verification code should only contain numbers'))

        if not user._kw_totp_try_setting(totp_secret, code):
            raise UserError(_(
                'Verification failed, please double-check the 6-digit code'))

        self._kw_finalize_session()
        return request.redirect(self._login_redirect(
            request.session.uid, redirect=None))

    @http.route(route='/web/login/totp', type='http', auth='public',
                methods=['GET', 'POST'], sitemap=False, website=True,
                multilang=False)
    def web_totp(self, redirect=None, **kwargs):
        if request.session.uid:
            return request.redirect(self._login_redirect(
                request.session.uid, redirect=redirect))

        if not request.session.get('pre_uid'):
            return request.redirect('/web/login')

        error = None
        user = self._get_pre_user()

        if request.httprequest.method == 'POST' and kwargs.get('totp_token'):
            try:
                with user._assert_can_auth(user=user.id):
                    user._totp_check(
                        int(re.sub(r'\s', '', kwargs['totp_token'])))
            except AccessDenied as e:
                error = str(e)
            except ValueError:
                error = _('Invalid authentication code format.')
            else:
                self._kw_finalize_session()
                request.session.touch()
                return request.redirect(self._login_redirect(
                    request.session.uid, redirect=redirect))

        request.session.touch()
        return request.render('auth_totp.auth_totp_form', {
            'user': user,
            'error': error,
            'redirect': redirect, })
