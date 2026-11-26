# Part of Odoo. See LICENSE file for full copyright and licensing details.
"""One place for one-time codes.

Every flow that sends someone a code (sign-up activation, email login, SMS login, checkout and
EMI phone checks) goes through `auth.otp`. It issues one code, delivers that same code on each
channel the flow allows (email, SMS), and checks it. Generation, hashing, expiry, wrong tries,
resend cooldown and rate limits live only here.

Channels: email is built in. SMS comes from another module (sms_nestsms), which overrides
`_otp_sms_available`, `_otp_send_sms`, `_otp_normalize_phone` and `_otp_sms_max_validity`.
"""
import ipaddress
import logging
import re
import secrets
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.http import request
from odoo.tools import consteq
from odoo.tools.misc import hmac

_logger = logging.getLogger(__name__)

DEFAULT_VALIDITY = timedelta(minutes=10)
RESEND_COOLDOWN = timedelta(seconds=60)
MAX_ATTEMPTS = 5            # wrong codes before a code dies
MAX_PER_TARGET_HOUR = 5     # codes per email address, and per phone number, per hour
MAX_PER_IP_HOUR = 10        # codes requested from one public IP address per hour
MAX_PER_COMPANY_HOUR = 200  # site-wide ceiling (ir.config_parameter auth_otp.max_per_hour)
CHANNELS = ('email', 'sms')


def _new_code():
    return f"{secrets.randbelow(10 ** 6):06d}"


def _new_token():
    return secrets.token_urlsafe(32)


def mask_email(email):
    local, _sep, domain = (email or '').partition('@')
    if len(local) > 2:
        local = f"{local[0]}{'*' * (len(local) - 2)}{local[-1]}"
    return f"{local}@{domain}" if domain else (email or '')


def mask_phone(phone):
    phone = phone or ''
    return f"{phone[:3]}*****{phone[-2:]}" if len(phone) > 5 else phone


class AuthOtp(models.Model):
    _name = 'auth.otp'
    _description = "One-Time Code"
    _order = 'id desc'
    _rec_name = 'purpose'

    purpose = fields.Char(required=True, readonly=True, index=True,
                          help="What the code is for: signup, login, email_login, checkout, emi...")
    user_id = fields.Many2one('res.users', readonly=True, ondelete='cascade', index='btree_not_null')
    email = fields.Char(readonly=True, index='btree_not_null')
    phone = fields.Char(readonly=True, index='btree_not_null', help="Normalised mobile number.")
    company_id = fields.Many2one('res.company', required=True, readonly=True)
    state = fields.Selection([
        ('sent', "Sent"),
        ('verified', "Verified"),
        ('replaced', "Replaced or expired"),
        ('blocked', "Too many wrong codes"),
        ('failed', "Not sent"),
    ], required=True, readonly=True, default='sent')
    channels = fields.Char(readonly=True, help="Where the code went: email, sms.")
    code_hash = fields.Char(readonly=True, groups='base.group_system')
    token_hash = fields.Char(readonly=True, index='btree_not_null', groups='base.group_system')
    salt = fields.Char(readonly=True, groups='base.group_system')
    sent_at = fields.Datetime(readonly=True, default=fields.Datetime.now)
    expires_at = fields.Datetime(readonly=True)
    attempts = fields.Integer(readonly=True, help="Wrong codes entered.")
    ip_address = fields.Char(readonly=True)
    failure_reason = fields.Char(readonly=True)

    # Policy and channel hooks
    # ------------------------------------------------------------------

    @api.model
    def _otp_policy(self, purpose, company):
        """How codes for `purpose` work: the channels it may use and how long a code lasts.
        Flow modules adjust it (a phone check is SMS only)."""
        return {'channels': CHANNELS, 'validity': DEFAULT_VALIDITY}

    @api.model
    def _otp_normalize_phone(self, phone):
        """The number codes are sent to and counted by, or False if it can't take one."""
        digits = re.sub(r'\D', '', phone or '')
        return digits or False

    @api.model
    def _otp_sms_available(self, purpose, company):
        """Whether codes for `purpose` can go by SMS (an SMS module says so)."""
        return False

    @api.model
    def _otp_sms_max_validity(self, purpose, company):
        """The longest a code texted for `purpose` may last (its approved text states it)."""
        return None

    def _otp_send_sms(self, code):
        """Text `code` to self.phone. Returns ``(ok, failure_reason)``."""
        return False, "No SMS channel is installed."

    def _otp_send_email(self, code, token, email_sender=None):
        """Email `code` (and the link token, if any) to self.email, with the caller's
        `email_sender(otp, code, token)` or the generic template."""
        self.ensure_one()
        try:
            with self.env.cr.savepoint():
                if email_sender:
                    email_sender(self, code, token)
                else:
                    template = self.env.ref('auth_otp.mail_template_otp_code')
                    template.sudo().with_context(otp_code=code, otp_minutes=self._otp_minutes()).send_mail(
                        self.id, force_send=True)
        except Exception as e:  # noqa: BLE001  never let a mail problem break the flow
            _logger.exception("Could not email a one-time code for %s", self.purpose)
            return False, str(e)
        return True, False

    # Issuing
    # ------------------------------------------------------------------

    @api.model
    def _otp_issue(self, purpose, *, user=None, email=None, phone=None, company=None,
                   with_link=False, email_sender=None):
        """Issue ONE code for `purpose` and deliver it on every channel the purpose allows and
        the person has: their email address and/or mobile number.

        `user`, else `email`, else `phone` identifies whose code it is (one live code each).

        Returns a dict: ``otp`` (record, or False), ``error`` (message for the person, or
        False), ``channels`` (where the code went), ``token`` (link token, with_link only).
        Never raises, so a refusal is committed and keeps counting towards the limits.
        """
        user = user or self.env['res.users']
        company = (company or user.company_id or self.env.company).sudo()
        email = (email or '').strip().lower() or False
        phone = self._otp_normalize_phone(phone) if phone else False
        result = {'otp': False, 'error': False, 'channels': [], 'token': False}

        policy = self._otp_policy(purpose, company)
        channels = []
        if email and 'email' in policy['channels']:
            channels.append('email')
        if phone and 'sms' in policy['channels'] and self._otp_sms_available(purpose, company):
            channels.append('sms')
        if not channels:
            if policy['channels'] == ('sms',) and not self._otp_sms_available(purpose, company):
                result['error'] = _("Codes by SMS are not available right now. Please try again later.")
            else:
                result['error'] = _("We have no way to send you a code.")
            return result

        Otp = self.sudo()
        subject = self._otp_subject_domain(user, email, phone)
        now = fields.Datetime.now()
        last = Otp.search([('purpose', '=', purpose)] + subject, limit=1)
        if last and now - last.sent_at < RESEND_COOLDOWN:
            result['error'] = _("We sent you a code less than a minute ago. Please wait a moment before asking again.")
            return result
        hour_ago = now - timedelta(hours=1)
        ip = request.httprequest.remote_addr if request else False
        if (email and Otp.search_count([('email', '=', email), ('sent_at', '>=', hour_ago)]) >= MAX_PER_TARGET_HOUR
                or phone and Otp.search_count([('phone', '=', phone), ('sent_at', '>=', hour_ago)]) >= MAX_PER_TARGET_HOUR
                or self._is_public_ip(ip)
                and Otp.search_count([('ip_address', '=', ip), ('sent_at', '>=', hour_ago)]) >= MAX_PER_IP_HOUR):
            result['error'] = _("Too many codes were requested. Please try again in an hour.")
            return result
        ceiling = int(self.env['ir.config_parameter'].sudo().get_param('auth_otp.max_per_hour', MAX_PER_COMPANY_HOUR))
        if Otp.search_count([('company_id', '=', company.id), ('sent_at', '>=', hour_ago)]) >= ceiling:
            _logger.error("One-time codes: %s reached its ceiling of %s codes an hour; refusing more.", company.name, ceiling)
            result['error'] = _("Codes are not available right now. Please try again later.")
            return result

        validity = policy['validity']
        sms_cap = self._otp_sms_max_validity(purpose, company) if 'sms' in channels else None
        if sms_cap:
            validity = min(validity, sms_cap)  # the texted message states how long it lasts

        Otp.search([('purpose', '=', purpose), ('state', '=', 'sent')] + subject).state = 'replaced'
        code = _new_code()
        token = _new_token() if with_link else False
        otp = Otp.create({
            'purpose': purpose,
            'user_id': user.id,
            'email': email,
            'phone': phone,
            'company_id': company.id,
            'salt': secrets.token_hex(8),
            'sent_at': now,
            'expires_at': now + validity,
            'ip_address': ip,
        })
        otp.write({
            'code_hash': otp._otp_hash('code', code),
            'token_hash': token and otp._otp_token_hash(token),
        })

        delivered, failures = [], []
        for channel in channels:
            if channel == 'email':
                ok, reason = otp._otp_send_email(code, token, email_sender)
            else:
                ok, reason = otp._otp_send_sms(code)
            if ok:
                delivered.append(channel)
            else:
                failures.append(f"{channel}: {reason}")
        if not delivered:
            otp.write({'state': 'failed', 'failure_reason': '; '.join(failures)})
            result['error'] = _("We could not send the code. Please try again in a few minutes.")
            return result
        otp.write({'channels': ','.join(delivered), 'failure_reason': '; '.join(failures) or False})
        result.update(otp=otp, channels=delivered, token=token)
        return result

    # Checking
    # ------------------------------------------------------------------

    @api.model
    def _otp_live(self, purpose, *, user=None, email=None, phone=None):
        """The code waiting to be entered for this person, if any (even expired)."""
        # Never leave a local `user` as None: Odoo's _() reads it from the frame for the language.
        user = user or self.env['res.users']
        subject = self._otp_subject_domain(
            user, (email or '').strip().lower() or False,
            self._otp_normalize_phone(phone) if phone else False,
        )
        if not subject:
            return self.browse()
        return self.sudo().search([('purpose', '=', purpose), ('state', '=', 'sent')] + subject, limit=1)

    @api.model
    def _otp_verify(self, purpose, code, *, user=None, email=None, phone=None):
        """Check `code` against this person's live code for `purpose`, using it up when it
        matches. Returns ``(record, False)``, or ``(False, message)`` saying why not. Never
        raises, so a wrong guess stays counted even when the caller shows an error."""
        user = user or self.env['res.users']
        otp = self._otp_live(purpose, user=user, email=email, phone=phone)
        if not otp:
            return False, _("This code can no longer be used. Ask for a new one.")
        if otp.expires_at <= fields.Datetime.now():
            otp.state = 'replaced'
            return False, _("This code has expired. Ask for a new one.")
        code = re.sub(r'\s', '', code or '')
        if not consteq(otp.code_hash, otp._otp_hash('code', code)):
            otp.attempts += 1
            left = MAX_ATTEMPTS - otp.attempts
            if left <= 0:
                otp.state = 'blocked'
                return False, _("That code is not right, and it cannot be used any more. Ask for a new one.")
            return False, _("That code is not right. %(left)s tries left.", left=left)
        otp.state = 'verified'
        return otp, False

    @api.model
    def _otp_verify_link(self, purpose, token):
        """The live code whose emailed link carries `token`, used up; ``(False, message)`` if
        the link is unknown, replaced by a newer one, or expired."""
        otp = token and self.sudo().search([
            ('purpose', '=', purpose), ('token_hash', '=', self._otp_token_hash(token)),
        ], limit=1)
        not_valid = _("This link is not valid, or a newer one was sent since.")
        if not otp:
            return False, not_valid
        subject = self._otp_subject_domain(otp.user_id, otp.email, otp.phone)
        newer = self.sudo().search_count([('purpose', '=', purpose), ('id', '>', otp.id)] + subject, limit=1)
        if newer or otp.state in ('verified', 'blocked', 'failed'):
            return False, not_valid
        if otp.expires_at <= fields.Datetime.now():
            # Said even once its code was retired for being late: the person needs to know why.
            if otp.state == 'sent':
                otp.state = 'replaced'
            return False, _("This link has expired.")
        if otp.state != 'sent':
            return False, not_valid
        otp.state = 'verified'
        return otp, False

    @api.model
    def _otp_close(self, purpose, *, user=None, email=None, phone=None):
        """Retire any live code for this person (they got in another way)."""
        user = user or self.env['res.users']
        self._otp_live(purpose, user=user, email=email, phone=phone).state = 'replaced'

    # Helpers
    # ------------------------------------------------------------------

    def _otp_hash(self, scope, value):
        self.ensure_one()
        return hmac(self.env(su=True), f'auth_otp.{scope}', f'{self.id}:{self.salt}:{value}')

    @api.model
    def _otp_token_hash(self, token):
        # Link tokens are long and random: no salt needed, so a link can be looked up by its hash.
        return hmac(self.env(su=True), 'auth_otp.link', token)

    @api.model
    def _otp_subject_domain(self, user, email, phone):
        if user:
            return [('user_id', '=', user.id)]
        if email:
            return [('email', '=', email)]
        if phone:
            return [('phone', '=', phone)]
        return []

    @api.model
    def _is_public_ip(self, ip):
        """Behind a reverse proxy without proxy_mode every request shows the proxy's private
        IP; capping that would cap the whole site."""
        try:
            return bool(ip) and ipaddress.ip_address(ip).is_global
        except ValueError:
            return False

    def _otp_minutes(self):
        self.ensure_one()
        return max(1, round((self.expires_at - self.sent_at).total_seconds() / 60))

    def _otp_sent_to(self):
        """Where this code went, masked for display: {'email': ..., 'sms': ...}."""
        self.ensure_one()
        channels = (self.channels or '').split(',')
        sent_to = {}
        if 'email' in channels:
            sent_to['email'] = mask_email(self.email)
        if 'sms' in channels:
            sent_to['sms'] = mask_phone(self.phone)
        return sent_to

    @api.autovacuum
    def _gc_old_codes(self):
        self.sudo().search([('sent_at', '<', fields.Datetime.now() - timedelta(days=30))]).unlink()
