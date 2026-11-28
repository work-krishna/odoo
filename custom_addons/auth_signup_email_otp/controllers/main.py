import logging
import time

from werkzeug.urls import url_encode

from odoo import _, fields, http
from odoo.exceptions import UserError
from odoo.http import request

from odoo.addons.auth_otp.models.auth_otp import MAX_ATTEMPTS
from odoo.addons.auth_signup.controllers.main import AuthSignupHome
from odoo.addons.auth_signup_email_otp.models.res_users import RESET
from odoo.addons.web.controllers.home import SIGN_UP_REQUEST_PARAMS, Home

_logger = logging.getLogger(__name__)

# Let the sign-up form's mobile number (shown when sign-up codes also go by SMS) through.
SIGN_UP_REQUEST_PARAMS.add('phone')

RESET_STATE = 'reset_password_code'    # where the reset code went, for this visitor
RESET_PROOF = 'reset_password_proof'   # the code was right: the visitor may set a password
RESET_COOLDOWN = 60                    # seconds between two codes for one visitor
RESET_PROOF_TTL = 15 * 60              # seconds left to choose the new password


def _local_url(url, default='/'):
    return url if url and url.startswith('/') and not url.startswith('//') and '\\' not in url else default


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
    def verify_email(self, code=None, send=None, redirect=None, **kwargs):
        user = request.env.user
        redirect = _local_url(redirect)
        if not user._signup_email_unverified():
            return request.redirect(redirect)
        values = {'email': user.email, 'redirect': redirect}
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
                    return request.render('auth_signup_email_otp.verify_email_done', {'redirect': redirect})
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


class PasswordResetByCode(AuthSignupHome):
    """Forgotten password: the person gets a code, by email or, where SMS codes are on for
    password resets, by SMS to the account's proven mobile number plus a different one by
    email. Either code lets them choose a new password. Odoo's emailed links (invitations,
    "Send Password Reset Instructions") keep working: they carry a token.

    The answers are the same whether or not an account matches, so the page can't tell who
    has one."""

    def _reset_values(self, **values):
        company = request.env.company
        Otp = request.env['auth.otp'].sudo()
        return {
            'sms_available': Otp._otp_sms_available(RESET, company),
            'validity': int(Otp._otp_policy(RESET, company)['validity'].total_seconds() // 60),
            **values,
        }

    def _reset_render(self, template, values):
        response = request.render(template, values)
        response.headers['Cache-Control'] = 'no-cache'
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        response.headers['Content-Security-Policy'] = "frame-ancestors 'self'"
        return response

    @http.route()
    def web_auth_reset_password(self, *args, **kw):
        qcontext = self.get_auth_signup_qcontext()
        if qcontext.get('token') or not qcontext.get('reset_password_enabled'):
            return super().web_auth_reset_password(*args, **kw)

        values = self._reset_values(login=(kw.get('login') or '').strip(), method='email')
        if request.httprequest.method == 'POST':
            login = values['login']
            method = 'sms' if kw.get('method') == 'sms' and values['sms_available'] else 'email'
            values['method'] = method
            state = request.session.get(RESET_STATE) or {}
            if not login:
                values['error'] = _("Enter your email address.")
            elif state.get('sent_at') and time.time() - state['sent_at'] < RESET_COOLDOWN:
                values['error'] = _("We sent you a code less than a minute ago. Please wait a moment before asking again.")
            else:
                user = request.env['res.users'].sudo()._reset_find_user(login)
                _logger.info("Password reset code asked for <%s> (%s) from %s: %s", login, method,
                             request.httprequest.remote_addr, f"user #{user.id}" if user else "no account")
                error = user and user._reset_send_code(by_sms=method == 'sms')['error']
                if error:
                    values['error'] = error
                else:
                    request.session[RESET_STATE] = {
                        'uid': user.id, 'login': login, 'method': method, 'sent_at': time.time(), 'decoy_attempts': 0,
                    }
                    return request.redirect('/web/reset_password/code')
        return self._reset_render('auth_signup_email_otp.reset_password_ask', values)

    @http.route('/web/reset_password/code', type='http', auth='public', website=True, sitemap=False,
                methods=['GET', 'POST'])
    def web_reset_password_code(self, code=None, **kw):
        state = dict(request.session.get(RESET_STATE) or {})
        if not state.get('login'):
            return request.redirect('/web/reset_password')
        values = self._reset_values(login=state['login'], method=state['method'])
        if request.httprequest.method == 'POST' and code is not None:
            user = request.env['res.users'].sudo().browse(state['uid']).exists()
            if not user:
                # No code went anywhere: answer exactly as for a wrong code, tries included.
                state['decoy_attempts'] += 1
                left = MAX_ATTEMPTS - state['decoy_attempts']
                if left == 0:
                    values['error'] = _("That code is not right, and it cannot be used any more. Ask for a new one.")
                elif left < 0:
                    values['error'] = _("This code can no longer be used. Ask for a new one.")
                else:
                    values['error'] = _("That code is not right. %(left)s tries left.", left=left)
                request.session[RESET_STATE] = state
            else:
                try:
                    user._reset_check_code(code)
                except UserError as error:
                    values['error'] = error.args[0]
                else:
                    request.session.pop(RESET_STATE, None)
                    request.session[RESET_PROOF] = {'uid': user.id, 'until': time.time() + RESET_PROOF_TTL}
                    return request.redirect('/web/reset_password/new')
        return self._reset_render('auth_signup_email_otp.reset_password_code', values)

    @http.route('/web/reset_password/new', type='http', auth='public', website=True, sitemap=False,
                methods=['GET', 'POST'])
    def web_reset_password_new(self, password=None, confirm_password=None, **kw):
        proof = request.session.get(RESET_PROOF) or {}
        user = proof.get('until', 0) > time.time() and request.env['res.users'].sudo().browse(proof.get('uid')).exists()
        if not user:
            request.session.pop(RESET_PROOF, None)
            return request.redirect('/web/reset_password')
        values = {'login': user.login}
        if request.httprequest.method == 'POST':
            if not password:
                values['error'] = _("Choose a new password.")
            elif password != confirm_password:
                values['error'] = _("The two passwords don't match. Please type them again.")
            else:
                try:
                    user._reset_set_password(password)
                except UserError as error:
                    values['error'] = error.args[0]
                else:
                    request.session.pop(RESET_PROOF, None)
                    return request.redirect('/web/login?' + url_encode({
                        'login': user.login, 'message': _("Your password is changed. Log in with your new password."),
                    }))
        return self._reset_render('auth_signup_email_otp.reset_password_new', values)
