# Part of Odoo. See LICENSE file for full copyright and licensing details.

"""SMS as a channel of the one-time-code engine (auth_otp).

auth.otp issues and checks every code; this module only delivers them by SMS, the NTA way:
through the purpose's approved NestSMS OTP template, filling its placeholders, and switching
the purpose off when NestSMS rejects the template.
"""
import logging
import re

from odoo import api, fields, models

from odoo.addons.auth_otp.models.auth_otp import DEFAULT_VALIDITY
from odoo.addons.sms_nestsms.tools.sms_api import nepal_mobile

_logger = logging.getLogger(__name__)

# The approved NestSMS templates say "valid for 10 minutes": keep the two in step.
OTP_VALIDITY = DEFAULT_VALIDITY

# Purposes whose point is proving the phone: their code must go by SMS only.
SMS_ONLY_PURPOSES = {'login', 'checkout', 'emi'}

# NestSMS errors that mean the template itself is unusable: stop the flow instead of
# retrying it for every customer.
TEMPLATE_ERROR_CODES = {
    'TEMPLATE_NOT_FOUND', 'MESSAGE_TYPE_MISMATCH', 'MESSAGE_AND_TEMPLATE', 'OTP_REQUIRES_TEMPLATE',
    'OTP_CONTENT_REQUIRES_TEMPLATE', 'TEMPLATE_VARIABLES_MISSING', 'TEMPLATE_VARIABLES_EMPTY',
    'INVALID_OTP_VARIABLE', 'UNRESOLVED_OTP_TEMPLATE_VARIABLES',
}

# Placeholders an approved template may use, by kind. NestSMS requires every variable an OTP
# template declares, filled and non-empty ("authorised dynamic variables"), so Odoo fills the
# ones it understands and refuses templates with any other.
PLACEHOLDER_RE = re.compile(r'\{(\w+)\}')
PLACEHOLDER_KINDS = {
    'code': {'otp', 'code', 'otpcode', 'verificationcode', 'pin', 'passcode'},
    'brand': {'companyname', 'company', 'appname', 'app', 'applicationname', 'brand', 'brandname',
              'sitename', 'systemname', 'storename', 'shopname'},
    'minutes': {'expiry', 'expires', 'expiresin', 'expiryminutes', 'expirytime', 'validity',
                'validityminutes', 'validfor', 'minutes', 'ttl'},
    'purpose': {'purpose'},
}
PURPOSE_WORDS = {
    'login': "login",
    'signup': "account registration",
    'checkout': "order confirmation",
    'emi': "EMI application",
}


def otp_template_values(content, purpose, brand, code):
    """Values for every placeholder in the template `content`: ``(values, unknown)``, where
    unknown lists the placeholders Odoo can't fill."""
    minutes = int(OTP_VALIDITY.total_seconds() // 60)
    values, unknown = {}, []
    for match in PLACEHOLDER_RE.finditer(content or ''):
        name = match.group(1)
        key = re.sub(r'[^a-z0-9]', '', name.lower())
        kind = next((kind for kind, names in PLACEHOLDER_KINDS.items() if key in names), None)
        if kind == 'code':
            values[name] = code
        elif kind == 'brand':
            values[name] = brand or ''
        elif kind == 'minutes':
            # "{expiry} minutes" wants the number; a bare "{expiry}" the whole duration.
            says_unit = re.match(r'\s*min', content[match.end():], re.IGNORECASE)
            values[name] = str(minutes) if says_unit else f"{minutes} minutes"
        elif kind == 'purpose':
            values[name] = PURPOSE_WORDS[purpose]
        elif name not in unknown:
            unknown.append(name)
    return values, unknown


def render_otp_template(content, values):
    """The text as the customer will get it."""
    return PLACEHOLDER_RE.sub(lambda match: values.get(match.group(1), match.group(0)), content or '')


OTP_PURPOSES = [
    ('login', "Website login"),
    ('signup', "Sign-up activation"),
    ('checkout', "Checkout phone check"),
    ('emi', "EMI application phone check"),
]


class AuthOtp(models.Model):
    _inherit = 'auth.otp'

    nestsms_message_id = fields.Char(string="NestSMS Message ID", readonly=True)

    @api.model
    def _otp_policy(self, purpose, company):
        policy = super()._otp_policy(purpose, company)
        if purpose in SMS_ONLY_PURPOSES:
            policy['channels'] = ('sms',)
        return policy

    @api.model
    def _otp_normalize_phone(self, phone):
        return nepal_mobile(phone)

    @api.model
    def _otp_sms_available(self, purpose, company):
        return purpose in dict(OTP_PURPOSES) and company._sms_otp_enabled(purpose)

    @api.model
    def _otp_sms_max_validity(self, purpose, company):
        return OTP_VALIDITY

    def _otp_send_sms(self, code):
        """Text `code` through the purpose's approved NestSMS template."""
        self.ensure_one()
        company = self.company_id.sudo()
        content = company._sms_otp_approved_text(self.purpose)
        variables, _unknown = otp_template_values(content, self.purpose, company.sms_brand_name, code)
        result = company._sms_nestsms_api()._nestsms_send_template(
            self.phone, company._sms_otp_template(self.purpose), variables or {'otp': code},
        )
        if result['ok']:
            self.nestsms_message_id = result['message_id']
            return True, False
        _logger.warning("SMS code for %s not sent: %s", self.purpose, result['reason'])
        if result['code'] in TEMPLATE_ERROR_CODES:
            company._sms_otp_set_approved(self.purpose, False)
            _logger.error(
                "NestSMS rejected the %s OTP template of %s (%s): SMS codes for it are off until an "
                "administrator chooses an approved template again in Settings.",
                self.purpose, company.name, result['code'],
            )
        return False, result['reason']
