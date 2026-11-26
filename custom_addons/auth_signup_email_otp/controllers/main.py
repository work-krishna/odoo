from werkzeug.urls import url_encode

from odoo import _, http
from odoo.exceptions import UserError
from odoo.http import request

from odoo.addons.web.controllers.home import Home


class SignupVerification(Home):

    def _signup_pending_user(self):
        """User halfway through logging in (password checked, email not verified yet)."""
        uid = request.session.get('pre_uid')
        return request.env['res.users'].sudo().browse(uid).exists() if uid else request.env['res.users']

    def _signup_finish_login(self, user, redirect):
        if user._mfa_url():  # e.g. two-factor authentication still to do
            return request.redirect(self._login_redirect(user.id, redirect=redirect))
        request.session.finalize(request.env)
        request.update_env(user=request.session.uid)
        request.update_context(**request.session.context)
        return request.redirect(self._login_redirect(request.session.uid, redirect=redirect))

    @http.route('/web/signup/verify', type='http', auth='public', website=True, sitemap=False,
                methods=['GET', 'POST'])
    def web_signup_verify(self, redirect=None, code=None, resend=None, **kwargs):
        if request.session.uid:
            return request.redirect(self._login_redirect(request.session.uid, redirect=redirect))
        user = self._signup_pending_user()
        if not user:
            return request.redirect('/web/login')
        if user.signup_email_verified:  # activated meanwhile, e.g. with the link on another device
            return self._signup_finish_login(user, redirect)

        values = {'redirect': redirect, 'validity': user._signup_validity()}
        if request.httprequest.method == 'POST':
            if resend:
                if user._signup_send_verification():
                    values['message'] = user._signup_message('resent')
                else:
                    values['error'] = user._signup_message('cooldown')
            else:
                try:
                    user._signup_check_code(code)
                except UserError as error:
                    values['error'] = error.args[0]
                else:
                    return self._signup_finish_login(user, redirect)
        elif not user._signup_has_valid_code() and user._signup_send_verification():
            # Back after the code expired (or it was used up): a fresh one is on its way.
            values['message'] = user._signup_message('expired')
        # Read last: a resend may have switched the channel.
        values.update(channel=user._signup_channel(), sent_to=user._signup_sent_to(), email=user._signup_sent_to())
        response = request.render('auth_signup_email_otp.signup_verify', values)
        response.headers['Cache-Control'] = 'no-cache'
        return response

    @http.route('/web/signup/activate', type='http', auth='public', website=True, sitemap=False,
                methods=['GET'])
    def web_signup_activate(self, token=None, **kwargs):
        try:
            user = request.env['res.users'].sudo()._signup_check_link(token)
        except UserError as error:
            return request.render('auth_signup_email_otp.signup_link_invalid', {'error': error.args[0]})
        if request.session.get('pre_uid') == user.id:
            return self._signup_finish_login(user, None)
        return request.redirect('/web/login?' + url_encode({
            'login': user.login, 'message': _("Your account is activated. Log in to continue."),
        }))
