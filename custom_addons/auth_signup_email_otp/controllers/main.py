from werkzeug.urls import url_encode

from odoo import _, fields, http
from odoo.exceptions import UserError
from odoo.http import request

from odoo.addons.auth_signup.controllers.main import AuthSignupHome
from odoo.addons.web.controllers.home import SIGN_UP_REQUEST_PARAMS, Home

# Let the sign-up form's mobile number (shown when sign-up codes also go by SMS) through.
SIGN_UP_REQUEST_PARAMS.add('phone')


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
        if user.signup_activated:  # activated meanwhile, e.g. with the link on another device
            return self._signup_finish_login(user, redirect)

        values = {'redirect': redirect}
        if request.httprequest.method == 'POST':
            if resend:
                sent, error = user._signup_send_verification()
                if sent:
                    values['message'] = user._signup_message('resent')
                else:
                    values['error'] = error
            else:
                try:
                    user._signup_check_code(code)
                except UserError as error:
                    values['error'] = error.args[0]
                else:
                    return self._signup_finish_login(user, redirect)
        elif not user._signup_has_valid_code() and user._signup_send_verification()[0]:
            # Back after the code expired (or it was used up): a fresh one is on its way.
            values['message'] = user._signup_message('expired')
        # Read last: a resend changes where the code went and how long it lasts.
        pending = user._signup_pending()
        values.update(
            sent_to=user._signup_sent_to(),
            validity=pending._otp_minutes() if pending else user._signup_validity(),
        )
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


    # Confirming the email address of an account activated by SMS
    # ------------------------------------------------------------------

    @http.route('/my/verify-email', type='http', auth='user', website=True, sitemap=False,
                methods=['GET', 'POST'])
    def verify_email(self, code=None, send=None, **kwargs):
        user = request.env.user
        if not user._signup_email_unverified():
            return request.redirect('/')
        values = {'email': user.email}
        if request.httprequest.method == 'POST':
            if send:
                sent, error = user._verify_email_send()
                if sent:
                    values['message'] = _("We emailed you a code and a link.")
                else:
                    values['error'] = error
            elif code is not None:
                try:
                    user._verify_email_check_code(code)
                except UserError as error:
                    values['error'] = error.args[0]
                else:
                    return request.render('auth_signup_email_otp.verify_email_done')
        pending = user._verify_email_pending()
        values.update(
            code_sent=bool(pending) and pending.expires_at > fields.Datetime.now(),
            validity=pending._otp_minutes() if pending else user._signup_validity(),
        )
        response = request.render('auth_signup_email_otp.verify_email', values)
        response.headers['Cache-Control'] = 'no-cache'
        return response

    @http.route('/web/verify-email', type='http', auth='public', website=True, sitemap=False, methods=['GET'])
    def verify_email_link(self, token=None, **kwargs):
        try:
            request.env['res.users'].sudo()._verify_email_check_link(token)
        except UserError as error:
            return request.render('auth_signup_email_otp.verify_email_link_invalid', {'error': error.args[0]})
        return request.render('auth_signup_email_otp.verify_email_done')


class SignupMobileNumber(AuthSignupHome):
    """Where sign-up codes also go by SMS, the sign-up form asks for the mobile number."""

    def get_auth_signup_qcontext(self):
        qcontext = super().get_auth_signup_qcontext()
        qcontext['signup_phone_enabled'] = request.env['auth.otp'].sudo()._otp_sms_available('signup', request.env.company)
        return qcontext

    def _prepare_signup_values(self, qcontext):
        values = super()._prepare_signup_values(qcontext)
        if qcontext.get('signup_phone_enabled') and not qcontext.get('token'):
            phone = (qcontext.get('phone') or '').strip()
            if not phone:
                raise UserError(_("Enter your mobile number: we also text your activation code to it."))
            values['phone'] = phone
        return values
