def migrate(cr, version):
    """Codes now come from auth_otp, with NestSMS as their SMS channel. Odoo forgets the old
    sms.nestsms.otp model but leaves its table behind: drop it."""
    cr.execute("DROP TABLE IF EXISTS sms_nestsms_otp CASCADE")
