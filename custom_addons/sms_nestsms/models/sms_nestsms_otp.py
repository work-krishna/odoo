# Part of Odoo. See LICENSE file for full copyright and licensing details.

import ipaddress
import logging
import re
import secrets
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.http import request
from odoo.tools import consteq
from odoo.tools.misc import hmac

from odoo.addons.sms_nestsms.tools.sms_api import nepal_mobile

_logger = logging.getLogger(__name__)

# The approved NestSMS templates say "valid for 10 minutes": keep the two in step.
OTP_VALIDITY = timedelta(minutes=10)
RESEND_COOLDOWN = timedelta(seconds=60)
MAX_ATTEMPTS = 5            # wrong codes before a code stops working
MAX_PER_NUMBER_HOUR = 5     # codes texted to one number per hour, all purposes together
MAX_PER_IP_HOUR = 10        # codes requested from one IP address per hour
MAX_PER_COMPANY_HOUR = 200  # site-wide ceiling (ir.config_parameter sms_nestsms.otp_max_per_hour)

OTP_PURPOSES = [
    ('login', "Website login"),
    ('signup', "Sign-up activation"),
    ('checkout', "Checkout phone check"),
    ('emi', "EMI application phone check"),
]


class SmsNestsmsOtp(models.Model):
    """A one-time code texted through an approved NestSMS OTP template.

    Only a keyed hash of the code is stored. Requests are capped per number and per IP
    address, so nobody can use the site to flood a phone or drain the NestSMS wallet
    ("SMS pumping"), which would also hurt the account's fair-send score.
    """
    _name = 'sms.nestsms.otp'
    _description = "SMS One-Time Code"
    _order = 'id desc'
    _rec_name = 'number'

    purpose = fields.Selection(OTP_PURPOSES, required=True, readonly=True)
    number = fields.Char(required=True, readonly=True, index=True, help="Nepali mobile number, 98XXXXXXXX.")
    company_id = fields.Many2one('res.company', required=True, readonly=True)
    state = fields.Selection([
        ('sent', "Sent"),
        ('verified', "Verified"),
        ('replaced', "Replaced by a newer code"),
        ('blocked', "Too many wrong codes"),
        ('failed', "Not sent"),
    ], required=True, readonly=True, default='sent')
    code_hash = fields.Char(readonly=True, groups='base.group_system')
    salt = fields.Char(readonly=True, groups='base.group_system')
    expires_at = fields.Datetime(readonly=True)
    attempts = fields.Integer(readonly=True, help="Wrong codes entered.")
    ip_address = fields.Char(readonly=True)
    nestsms_message_id = fields.Char(readonly=True)
    failure_reason = fields.Char(readonly=True)

    def _hash(self, code):
        self.ensure_one()
        return hmac(self.env(su=True), 'sms_nestsms.otp', f'{self.purpose}:{self.number}:{self.salt}:{code}')

    # Sending
    # ------------------------------------------------------------------

    @api.model
    def _nestsms_send(self, purpose, number, company=None, code=None):
        """Text a new code for `purpose` to `number`: `code` when the caller generated and
        checks it itself (sign-up), a fresh one otherwise.

        Returns ``(record, False)`` once NestSMS accepted it, or ``(False, message)`` with a
        message to show the customer. Never raises, so a refusal is still committed and
        keeps counting towards the limits.
        """
        company = (company or self.env.company).sudo()
        mobile = nepal_mobile(number)
        if not mobile:
            return False, _("Enter a Nepali mobile number (98XXXXXXXX).")
        template_id = company._sms_otp_template(purpose)
        if not company.sms_nestsms_api_key or not template_id:
            _logger.warning("SMS code for %s requested, but %s has no NestSMS key or template for it.", purpose, company.name)
            return False, _("Codes by SMS are not available right now. Please try again later.")

        Otp = self.sudo()
        now = fields.Datetime.now()
        last = Otp.search([('purpose', '=', purpose), ('number', '=', mobile)], limit=1)
        if last and now - last.create_date < RESEND_COOLDOWN:
            return False, _("A code was just sent. Please wait a minute before asking for another one.")
        hour_ago = now - timedelta(hours=1)
        ip = request.httprequest.remote_addr if request else False
        if (Otp.search_count([('number', '=', mobile), ('create_date', '>=', hour_ago)]) >= MAX_PER_NUMBER_HOUR
                or self._is_public_ip(ip) and Otp.search_count([('ip_address', '=', ip), ('create_date', '>=', hour_ago)]) >= MAX_PER_IP_HOUR):
            return False, _("Too many codes were requested. Please try again in an hour.")
        company_cap = int(self.env['ir.config_parameter'].sudo().get_param('sms_nestsms.otp_max_per_hour', MAX_PER_COMPANY_HOUR))
        if Otp.search_count([('company_id', '=', company.id), ('create_date', '>=', hour_ago)]) >= company_cap:
            _logger.error("SMS codes: %s reached its ceiling of %s codes an hour; refusing more.", company.name, company_cap)
            return False, _("Codes by SMS are not available right now. Please try again later.")

        Otp.search([('purpose', '=', purpose), ('number', '=', mobile), ('state', '=', 'sent')]).state = 'replaced'
        code = code or f"{secrets.randbelow(10 ** 6):06d}"
        otp = Otp.create({
            'purpose': purpose,
            'number': mobile,
            'company_id': company.id,
            'salt': secrets.token_hex(8),
            'expires_at': now + OTP_VALIDITY,
            'ip_address': ip,
        })
        otp.code_hash = otp._hash(code)

        sms_api = company._get_sms_api_class()(self.env)
        sms_api._set_company(company)
        result = sms_api._nestsms_send_template(mobile, template_id, {'otp': code})
        if not result['ok']:
            otp.write({'state': 'failed', 'failure_reason': result['reason']})
            _logger.warning("SMS code for %s to %s not sent: %s", purpose, otp._masked_number(), result['reason'])
            return False, _("We could not send the code. Please try again in a few minutes.")
        otp.nestsms_message_id = result['message_id']
        return otp, False

    # Checking
    # ------------------------------------------------------------------

    @api.model
    def _nestsms_verify(self, purpose, number, code):
        """Check `code` against the live code last texted to `number` for `purpose`, and use
        it up when it matches.

        Returns ``(record, False)`` on success, or ``(False, message)`` saying why not. Never
        raises, so a wrong guess stays counted even when the caller shows an error.
        """
        mobile = nepal_mobile(number)
        otp = mobile and self.sudo().search([('purpose', '=', purpose), ('number', '=', mobile), ('state', '=', 'sent')], limit=1)
        if not otp:
            return False, _("Ask for a code first.")
        if otp.expires_at <= fields.Datetime.now():
            otp.state = 'replaced'
            return False, _("This code has expired. Ask for a new one.")
        code = re.sub(r'\s', '', code or '')
        if not consteq(otp.code_hash, otp._hash(code)):
            otp.attempts += 1
            left = MAX_ATTEMPTS - otp.attempts
            if left <= 0:
                otp.state = 'blocked'
                return False, _("That code is not right, and it can no longer be used. Ask for a new one.")
            return False, _("That code is not right. %(left)s tries left.", left=left)
        otp.state = 'verified'
        return otp, False

    @api.model
    def _is_public_ip(self, ip):
        """Behind a reverse proxy that doesn't forward the client address (no proxy_mode),
        every request shows the proxy's private IP; capping that would cap the whole site."""
        try:
            return bool(ip) and ipaddress.ip_address(ip).is_global
        except ValueError:
            return False

    def _masked_number(self):
        self.ensure_one()
        return f"{self.number[:3]}*****{self.number[-2:]}"

    @api.autovacuum
    def _gc_old_codes(self):
        self.sudo().search([('create_date', '<', fields.Datetime.now() - timedelta(days=30))]).unlink()
