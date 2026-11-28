def migrate(cr, version):
    # Sign-ups still waiting to confirm their email address still owe them the welcome email.
    cr.execute("UPDATE res_users SET signup_welcome_pending = TRUE WHERE signup_email_verified = FALSE")
