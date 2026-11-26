# -*- coding: utf-8 -*-
import time

from odoo import models
from odoo.exceptions import AccessDenied
from odoo.http import request
from odoo.tools import consteq

from odoo.addons.i8_otp_login.controllers.main import CREDENTIAL_TYPE, PROOF_KEY


class ResUsers(models.Model):
    _inherit = 'res.users'

    def _check_credentials(self, credential, env):
        if credential.get('type') != CREDENTIAL_TYPE:
            return super()._check_credentials(credential, env)
        # Valid only right after /otp-login/verify accepted the emailed code in this very
        # browser session, and only for customer accounts.
        proof = request.session.get(PROOF_KEY) if request else None
        user = self.env.user
        if not (
            proof and user.share
            and proof.get('uid') == user.id
            and time.time() < proof.get('until', 0)
            and consteq(proof.get('proof') or '', credential.get('proof') or '')
        ):
            raise AccessDenied()
        # 'default': a customer who turned on two-factor authentication still gets asked.
        return {'uid': user.id, 'auth_method': CREDENTIAL_TYPE, 'mfa': 'default'}
