def migrate(cr, version):
    """Codes now come from auth_otp. Odoo forgets the old auth.signup.verification model but
    leaves its table behind: drop it. Accounts waiting for activation simply get a new code
    the next time they open the activation page."""
    cr.execute("DROP TABLE IF EXISTS auth_signup_verification CASCADE")
