import base64
import functools
import io
import logging
import os
import re

import qrcode
import werkzeug.urls
from odoo import models
from odoo.addons.auth_totp.models.totp import TOTP
from odoo.http import request

_logger = logging.getLogger(__name__)

TOTP_SECRET_SIZE = 160


class User(models.Model):
    _inherit = "res.users"

    def _mfa_type(self):
        if self.id == self.env.ref('base.user_root').id:
            return super()._mfa_type()
        return 'totp'

    def _mfa_url(self):
        if not self.totp_enabled:
            return '/kw_2fa/setup_totp'
        return super()._mfa_url()

    def _kw_generate_totp_qr_data(self, issuer=None):
        secret_bytes = TOTP_SECRET_SIZE // 8
        secret = base64.b32encode(os.urandom(secret_bytes)).decode()

        issuer = issuer or self.company_id.display_name
        url = werkzeug.urls.url_unparse((
            'otpauth',
            'totp',
            werkzeug.urls.url_quote(f'{issuer}:{self.login}', safe=':'),
            werkzeug.urls.url_encode({
                'secret': secret,
                'issuer': issuer,
                'algorithm': 'SHA1',
                'digits': 6,
                'period': 30,
            }),
            '',
        ))

        data = io.BytesIO()
        qrcode.make(url).save(data, format='PNG')

        return {'totp_secret': secret,
                'totp_qr': base64.b64encode(data.getvalue()).decode(),
                'formatted_totp_secret': ' '.join(
                    secret[i:i + 4] for i in range(0, len(secret), 4)), }

    def _kw_totp_try_setting(self, secret, code):
        self.ensure_one()

        if self.totp_enabled:
            return False

        compress = functools.partial(re.sub, r'\s', '')
        secret = compress(secret).upper()

        if TOTP(base64.b32decode(secret)).match(code) is None:
            return False

        self.sudo().totp_secret = secret

        if request:
            self.env.flush_all()
            request.session.session_token = \
                self.env.user._compute_session_token(request.session.sid)

        return True
