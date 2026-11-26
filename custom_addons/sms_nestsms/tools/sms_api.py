# Part of Odoo. See LICENSE file for full copyright and licensing details.
"""NestSMS (https://nestsms.com) as Odoo's SMS provider.

The NestSMS account is bound by Nepal Telecommunications Authority (NTA) rules. This file
keeps the ones that code can keep:

- Domestic routes only. Every SMS goes to NestSMS; nothing falls back to Odoo IAP or
  Twilio (both route abroad). A number that isn't a Nepali mobile is refused, not rerouted.
- OTPs only through an admin-approved NestSMS OTP template. Plain text that reads like a
  one-time code is refused here, before NestSMS sees it: NestSMS blocks it too
  (OTP_CONTENT_REQUIRES_TEMPLATE), and repeated attempts can cost the account its OTP
  service.
- Fair sending. Errors that would repeat for every message (bad key, empty wallet, rate
  limit, NestSMS unreachable) stop the batch instead of hammering the API.
"""
import logging
import re
from collections import namedtuple
from urllib.parse import urlencode

import requests

from odoo import _
from odoo.addons.sms.tools.sms_api import SmsApiBase

_logger = logging.getLogger(__name__)

NESTSMS_API_URL = 'https://auth.nestsms.com/api/v1'
TIMEOUT = 10  # seconds

_UUID_RE = re.compile(r'[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}')

# One NestSMS answer: `data` is the body's "data" (or "template") object, or the body itself.
NestSmsReply = namedtuple('NestSmsReply', 'ok data code reason stops_batch status')

# Nepali mobiles: ten digits starting 96, 97 or 98 (Smart, NTC, Ncell).
_NEPAL_MOBILE_RE = re.compile(r'9[678]\d{8}')

# One-time-code wording, together with a 4-8 digit number somewhere in the text.
_OTP_WORDS_RE = re.compile(
    r'\b(?:otp|one[\s-]?time|pass\s?code|pin|'
    r'(?:verification|verify|security|authentication|auth|login|access)\s+code)\b',
    re.IGNORECASE,
)
_CODE_DIGITS_RE = re.compile(r'(?<!\d)\d{4,8}(?!\d)')
# "code" followed closely by a bare number, e.g. "Your code is 482913".
_CODE_NEAR_DIGITS_RE = re.compile(r'\bcode\b\D{0,15}(?<!\d)\d{4,8}(?!\d)', re.IGNORECASE)


def nepal_mobile(number):
    """Return the ten-digit national form NestSMS expects (98XXXXXXXX), or False when
    `number` isn't a Nepali mobile number."""
    digits = re.sub(r'\D', '', number or '')
    for prefix in ('00977', '977'):
        if digits.startswith(prefix) and len(digits) == len(prefix) + 10:
            digits = digits[len(prefix):]
            break
    return digits if _NEPAL_MOBILE_RE.fullmatch(digits) else False


# GSM 03.38 basic set plus its extension table. A single character outside it makes the
# whole SMS Unicode: 70 characters per credit instead of 160.
GSM7_CHARS = frozenset(
    "@\u00a3$\u00a5\u00e8\u00e9\u00f9\u00ec\u00f2\u00c7\n\u00d8\u00f8\r\u00c5\u00e5\u0394_\u03a6\u0393\u039b\u03a9\u03a0\u03a8\u03a3\u0398\u039e"
    "\u00c6\u00e6\u00df\u00c9 !\"#\u00a4%&'()*+,-./0123456789:;<=>?\u00a1"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ\u00c4\u00d6\u00d1\u00dc\u00a7\u00bf"
    "abcdefghijklmnopqrstuvwxyz\u00e4\u00f6\u00f1\u00fc\u00e0"
    "\f^{}\\[~]|\u20ac"
)


def is_gsm7(text):
    """Whether `text` fits the GSM-7 alphabet (160 characters per SMS credit)."""
    return all(char in GSM7_CHARS for char in text or '')


def looks_like_otp(text):
    """Whether plain `text` reads like a one-time code, which NTA rules forbid outside an
    approved OTP template."""
    text = text or ''
    return bool(
        (_OTP_WORDS_RE.search(text) and _CODE_DIGITS_RE.search(text))
        or _CODE_NEAR_DIGITS_RE.search(text)
    )


class SmsApiNestSms(SmsApiBase):
    # Result states of `_send_sms_batch` -> sms.sms failure types. Only types that exist on
    # sms.sms, mail.notification and mailing.trace alike; the failure reason says the rest.
    PROVIDER_TO_SMS_FAILURE_TYPE = SmsApiBase.PROVIDER_TO_SMS_FAILURE_TYPE | {
        'nestsms_account': 'sms_acc',
        'nestsms_balance': 'sms_credit',
        'nestsms_domestic_only': 'sms_country_not_supported',
        'nestsms_otp_template': 'sms_registration_needed',
        'nestsms_rejected': 'unknown',
    }

    # NestSMS error codes, from their API documentation ("Error Codes Reference" and the
    # template "Rules & Validation"). Codes not listed here count as 'nestsms_rejected'.
    ERROR_CODE_TO_STATE = {
        'NO_API_KEY': 'nestsms_account',
        'INVALID_API_KEY': 'nestsms_account',
        'API_KEY_EXPIRED': 'nestsms_account',
        'ORG_INACTIVE': 'nestsms_account',
        'IP_RESTRICTED': 'nestsms_account',
        'INSUFFICIENT_PERMISSIONS': 'nestsms_account',
        'NO_SENDER_ID': 'nestsms_account',
        'INVALID_SENDER_ID': 'nestsms_account',
        'ACCESS_DENIED': 'nestsms_account',
        'INSUFFICIENT_BALANCE': 'nestsms_balance',
        'MISSING_TO': 'sms_number_missing',
        'INVALID_TO_FORMAT': 'wrong_number_format',
        'OTP_REQUIRES_TEMPLATE': 'nestsms_otp_template',
        'OTP_CONTENT_REQUIRES_TEMPLATE': 'nestsms_otp_template',
        'TEMPLATE_VARIABLES_MISSING': 'nestsms_otp_template',
        'TEMPLATE_VARIABLES_EMPTY': 'nestsms_otp_template',
        'TEMPLATE_NOT_FOUND': 'nestsms_otp_template',
        'INVALID_OTP_VARIABLE': 'nestsms_otp_template',
        'UNRESOLVED_OTP_TEMPLATE_VARIABLES': 'nestsms_otp_template',
        'MESSAGE_TYPE_MISMATCH': 'nestsms_otp_template',
        'RATE_LIMIT_EXCEEDED': 'server_error',
    }
    # Errors that every remaining message of the batch would hit as well.
    STOP_BATCH_CODES = {
        code for code, state in ERROR_CODE_TO_STATE.items()
        if state in ('nestsms_account', 'nestsms_balance')
    } | {'RATE_LIMIT_EXCEEDED'}

    # Plain texts (raw message flow)
    # ------------------------------------------------------------------

    def _send_sms_batch(self, messages, delivery_reports_url=False):
        """Send each SMS with its own NestSMS call. See the base method for the arguments.

        Returns one dict per number: ``uuid``, ``state``, ``failure_reason`` and, once NestSMS
        accepted it, ``nestsms_message_id`` (their key for delivery-status lookups).
        """
        api_key = self._nestsms_api_key()
        stop = None  # (state, reason) given to every remaining number once the batch must stop
        if not api_key:
            stop = ('nestsms_account', self._nestsms_no_key_reason())
        session = requests.Session()
        results = []
        for message in messages:
            content = message.get('content') or ''
            is_otp = looks_like_otp(content)
            for number_info in message.get('numbers') or []:
                number = number_info.get('number')
                to = nepal_mobile(number)
                message_id = False
                if stop:
                    state, reason = stop
                elif not number:
                    state, reason = 'sms_number_missing', False
                elif not to:
                    state, reason = 'nestsms_domestic_only', _(
                        "%s is not a Nepali mobile number. NestSMS only sends within Nepal "
                        "(NTA allows domestic routes only).", number,
                    )
                elif is_otp:
                    state, reason = 'nestsms_otp_template', _(
                        "This text reads like a one-time code. NTA rules allow OTPs only "
                        "through an approved NestSMS OTP template, not as plain text.",
                    )
                else:
                    reply = self._nestsms_call(session, api_key, 'POST', '/sms/send', {
                        'to': to,
                        'message': content,
                        # Anything outside GSM-7 (Nepali script, the rupee sign) must go as
                        # Unicode or it arrives garbled.
                        'type': 'text' if is_gsm7(content) else 'unicode',
                        'message_type': 'transactional',
                    })
                    if reply.ok:
                        state, reason, message_id = 'success', False, reply.data.get('message_id')
                    else:
                        state, reason = self._nestsms_error_state(reply), reply.reason
                        if reply.stops_batch:
                            stop = (state, reason)
                results.append({
                    'uuid': number_info['uuid'],
                    'state': state,
                    'failure_reason': reason,
                    'nestsms_message_id': message_id and str(message_id),
                })
        return results

    def _nestsms_error_state(self, reply):
        state = self.ERROR_CODE_TO_STATE.get(reply.code)
        if not state:
            state = 'server_error' if not reply.code or (reply.status or 0) >= 500 else 'nestsms_rejected'
        return state

    # Approved templates (required for OTPs)
    # ------------------------------------------------------------------

    def _nestsms_send_template(self, number, template_id, variables, message_type='otp'):
        """Send one SMS from an approved NestSMS template, filling in `variables`.

        Returns a dict: ``ok``, ``message_id``, ``code`` (NestSMS error code) and ``reason``.
        """
        api_key = self._nestsms_api_key()
        to = nepal_mobile(number)
        if not api_key:
            return {'ok': False, 'message_id': False, 'code': 'NO_API_KEY', 'reason': self._nestsms_no_key_reason()}
        if not to:
            return {'ok': False, 'message_id': False, 'code': 'INVALID_TO_FORMAT',
                    'reason': _("%s is not a Nepali mobile number.", number)}
        if not _UUID_RE.fullmatch(template_id or ''):
            return {'ok': False, 'message_id': False, 'code': 'TEMPLATE_NOT_FOUND',
                    'reason': _("The NestSMS template ID is missing or malformed.")}
        reply = self._nestsms_call(requests.Session(), api_key, 'POST', '/sms/send', {
            'to': to,
            'template_id': template_id,
            'message_type': message_type,
            'variables': variables,
        })
        message_id = reply.data.get('message_id') if reply.ok else False
        return {'ok': reply.ok, 'message_id': message_id and str(message_id), 'code': reply.code, 'reason': reply.reason}

    def _nestsms_list_templates(self, message_type=None, max_pages=20):
        """The organisation's active templates (dicts), following NestSMS's pagination
        (10 a page). Fetches a template's text separately when the list leaves it out.

        Returns ``(templates, error)``: error is False, or NestSMS's reason for refusing.
        """
        templates, offset = [], 0
        for _page in range(max_pages):
            query = {'offset': offset}
            if message_type:
                query['message_type'] = message_type
            reply = self._nestsms_get('/sms/templates?' + urlencode(query))
            if not reply.ok:
                return templates, reply.reason
            page = [template for template in reply.data.get('templates') or [] if isinstance(template, dict)]
            templates += page
            total = (reply.data.get('pagination') or {}).get('total')
            offset += len(page)
            if not page or not isinstance(total, int) or offset >= total:
                break
        if message_type:
            templates = [template for template in templates if template.get('message_type', message_type) == message_type]
        for template in templates:
            if 'content' not in template and template.get('id'):
                detail = self._nestsms_get_template(str(template['id']))
                if detail.ok:
                    template['content'] = detail.data.get('content') or ''
        return templates, False

    def _nestsms_get_template(self, template_id):
        """The NestSMS template `template_id` (dict with content, message_type, is_verified...)."""
        if not _UUID_RE.fullmatch(template_id or ''):
            return NestSmsReply(False, {}, 'TEMPLATE_NOT_FOUND', _("That is not a NestSMS template ID."), False, None)
        return self._nestsms_get('/sms/templates/' + template_id)

    # Account and delivery status
    # ------------------------------------------------------------------

    def _nestsms_get_balance(self):
        return self._nestsms_get('/sms/balance')

    def _nestsms_get_status(self, message_id):
        if not _UUID_RE.fullmatch(message_id or ''):
            return NestSmsReply(False, {}, 'NOT_FOUND', _("Unknown NestSMS message ID."), False, None)
        return self._nestsms_get('/sms/status/' + message_id)

    # Plumbing
    # ------------------------------------------------------------------

    def _nestsms_api_key(self):
        return (self.company or self.env.company).sudo().sms_nestsms_api_key

    def _nestsms_no_key_reason(self):
        return _(
            "No NestSMS API key is set for %s (Settings > General Settings > Send SMS).",
            (self.company or self.env.company).name,
        )

    def _nestsms_get(self, path):
        api_key = self._nestsms_api_key()
        if not api_key:
            return NestSmsReply(False, {}, 'NO_API_KEY', self._nestsms_no_key_reason(), True, None)
        return self._nestsms_call(requests.Session(), api_key, 'GET', path)

    def _nestsms_call(self, session, api_key, method, path, payload=None):
        """One NestSMS request, answered as a `NestSmsReply`. Never raises."""
        try:
            response = self._nestsms_request(session, api_key, method, path, payload)
        except requests.exceptions.RequestException as e:
            _logger.warning("NestSMS: could not reach the API: %s", e)
            return NestSmsReply(False, {}, '', _("Could not reach NestSMS: %s", e), True, None)

        try:
            body = response.json()
        except ValueError:
            body = None
        if not isinstance(body, dict):
            body = {}

        if response.ok and body.get('success') is not False:
            data = body.get('data') if isinstance(body.get('data'), dict) else body.get('template')
            return NestSmsReply(True, data if isinstance(data, dict) else body, '', False, False, response.status_code)

        code = body.get('code') or ''
        detail = body.get('message') or body.get('error') or response.reason or ''
        reason = _("NestSMS refused the request (%(code)s): %(detail)s", code=code or response.status_code, detail=detail)
        if body.get('missing_variables'):
            reason += ' ' + _("Missing template variables: %s.", ', '.join(map(str, body['missing_variables'])))
        if code == 'IP_RESTRICTED' and body.get('your_ip'):
            reason += ' ' + _(
                "NestSMS sees this server as %s: add that address to the API key's IP whitelist in NestSMS.",
                body['your_ip'],
            )
        if code == 'RATE_LIMIT_EXCEEDED' and body.get('retry_after'):
            reason += ' ' + _("Resend after %s seconds.", body['retry_after'])
        _logger.warning("NestSMS: %s %s refused, HTTP %s, code %s", method, path.split('/')[2] if path.count('/') > 1 else path,
                        response.status_code, code or '-')
        stops_batch = code in self.STOP_BATCH_CODES or response.status_code >= 500
        return NestSmsReply(False, body, code, reason, stops_batch, response.status_code)

    def _nestsms_request(self, session, api_key, method, path, payload=None):
        """The only place that talks to NestSMS (tests replace it)."""
        return session.request(
            method,
            NESTSMS_API_URL + path,
            json=payload,
            headers={'X-API-Key': api_key, 'Accept': 'application/json'},
            timeout=TIMEOUT,
        )
