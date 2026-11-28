from odoo import models
from odoo.tools import email_normalize


def _normalized(email):
    return email_normalize(email or '') or (email or '').strip().lower()


class ResPartner(models.Model):
    _inherit = 'res.partner'

    def write(self, vals):
        if 'email' not in vals:
            return super().write(vals)
        before = {partner.id: _normalized(partner.email) for partner in self}
        result = super().write(vals)
        # A customer's new address isn't proven yet: they are asked to confirm it.
        changed = self.filtered(lambda partner: _normalized(partner.email) != before[partner.id])
        users = changed.sudo().user_ids.filtered(lambda user: user.share and user.signup_email_verified)
        if users:
            users.signup_email_verified = False
        return result
