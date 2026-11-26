# Part of Odoo. See LICENSE file for full copyright and licensing details.

import re

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from odoo.addons.sms_nestsms.tools.sms_api import SmsApiNestSms

OTP_VARIABLE_RE = re.compile(r'\{(\w+)\}')


class ResCompany(models.Model):
    _inherit = 'res.company'

    sms_nestsms_api_key = fields.Char(
        string="NestSMS API Key", groups='base.group_system', copy=False,
        help="Created in the NestSMS dashboard under API Integration > API Token.",
    )
    sms_brand_name = fields.Char(
        string="SMS Brand Name",
        help="One word that opens every text, e.g. 'Flagship-Store' gives 'Flagship-Store: Your order ...'. "
             "NTA requires OTP texts to start with the app or system name as one word, then a colon.",
    )

    # One switch and one approved NestSMS OTP template per purpose (see sms.nestsms.otp).
    # Each flow module shows its own pair in Settings.
    sms_otp_login = fields.Boolean(string="SMS Codes for Website Login")
    sms_otp_login_template = fields.Char(string="Login OTP Template ID")
    sms_otp_signup = fields.Boolean(string="SMS Codes for Sign-up Activation")
    sms_otp_signup_template = fields.Char(string="Sign-up OTP Template ID")
    sms_otp_checkout = fields.Boolean(string="SMS Codes at Checkout")
    sms_otp_checkout_template = fields.Char(string="Checkout OTP Template ID")
    sms_otp_emi = fields.Boolean(string="SMS Codes for EMI Applications")
    sms_otp_emi_template = fields.Char(string="EMI OTP Template ID")

    @api.constrains('sms_brand_name')
    def _check_sms_brand_name(self):
        for company in self:
            brand = company.sms_brand_name
            # One word: letters and digits, hyphens only inside (Flagship-Store), no spaces.
            if brand and not (2 <= len(brand) <= 20 and re.fullmatch(r'[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*', brand)):
                raise ValidationError(_(
                    "The SMS brand name must be a single word of 2 to 20 letters or digits, without spaces; "
                    "a hyphen may join its parts, e.g. Flagship-Store."
                ))

    def _get_sms_api_class(self):
        # NestSMS only: no fallback to Odoo IAP, whose route is international.
        self.ensure_one()
        return SmsApiNestSms

    def _sms_nestsms_api(self):
        self.ensure_one()
        sms_api = self._get_sms_api_class()(self.env)
        sms_api._set_company(self)
        return sms_api

    # One-time codes
    # ------------------------------------------------------------------

    def _sms_otp_template(self, purpose):
        self.ensure_one()
        return (self.sudo()[f'sms_otp_{purpose}_template'] or '').strip()

    def _sms_otp_enabled(self, purpose):
        """Whether codes for `purpose` are switched on and can actually be sent."""
        self.ensure_one()
        company = self.sudo()
        return bool(company[f'sms_otp_{purpose}'] and company._sms_otp_template(purpose) and company.sms_nestsms_api_key)

    def _sms_otp_check_template(self, purpose):
        """Ask NestSMS about the purpose's template. Returns ``(content, problems)``, where
        problems lists, in sentences, whatever stops it from working or breaks NTA rules."""
        from odoo.addons.sms_nestsms.models.sms_nestsms_otp import OTP_VALIDITY  # noqa: PLC0415
        self.ensure_one()
        template_id = self._sms_otp_template(purpose)
        if not template_id:
            return '', [_("Paste the ID of the approved NestSMS OTP template first.")]
        reply = self._sms_nestsms_api()._nestsms_get_template(template_id)
        if not reply.ok:
            return '', [reply.reason]
        template = reply.data
        content = template.get('content') or ''
        problems = []
        if template.get('is_verified') is False:
            problems.append(_("NestSMS has not approved this template yet."))
        if template.get('is_active') is False:
            problems.append(_("This template is switched off in NestSMS."))
        if template.get('message_type') and template['message_type'] != 'otp':
            problems.append(_("Its message type is %s; it must be OTP.", template['message_type']))
        if content:
            variables = set(OTP_VARIABLE_RE.findall(content))
            if 'otp' not in variables:
                problems.append(_("Its text has no {otp} placeholder for the code."))
            if variables - {'otp'}:
                problems.append(_(
                    "Its text also has %s; Odoo only fills in {otp}.",
                    ', '.join('{%s}' % name for name in sorted(variables - {'otp'})),
                ))
            brand = self.sms_brand_name
            if not brand:
                problems.append(_("Set the SMS brand name: NTA requires OTP texts to start with it."))
            elif not content.startswith(brand + ':'):
                problems.append(_("NTA requires the text to start with \"%s:\".", brand))
            minutes = re.search(r'(\d+)\s*min', content, re.IGNORECASE)
            validity = int(OTP_VALIDITY.total_seconds() // 60)
            if minutes and int(minutes.group(1)) != validity:
                problems.append(_(
                    "The text says %(said)s minutes, but codes expire after %(real)s.",
                    said=minutes.group(1), real=validity,
                ))
        return content, problems
