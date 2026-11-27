def migrate(cr, version):
    """Each channel now gets its own code (email_code_hash, sms_code_hash). Codes issued before
    the upgrade only have the old shared hash, which Odoo drops: retire them. People ask for a
    new code; the sign-up activation page sends one by itself."""
    cr.execute("UPDATE auth_otp SET state = 'replaced' WHERE state = 'sent'")
