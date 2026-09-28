from odoo import fields, models


class AuthSignupVerification(models.Model):
    """The code and activation link last emailed to an account that is not
    activated yet. Only keyed hashes are stored, never the code or link."""
    _name = 'auth.signup.verification'
    _description = 'Sign-up Email Verification'

    user_id = fields.Many2one('res.users', required=True, ondelete='cascade', index=True)
    code_hash = fields.Char(required=True)
    token_hash = fields.Char(required=True, index=True)
    expires_at = fields.Datetime(required=True)
    sent_at = fields.Datetime(required=True)
    attempts = fields.Integer(help="Wrong codes entered since this one was sent.")

    _user_uniq = models.Constraint('unique(user_id)', 'An account has one pending activation at a time.')
