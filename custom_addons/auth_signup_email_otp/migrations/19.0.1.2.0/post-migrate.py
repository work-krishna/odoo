def migrate(cr, version):
    """Activation is now its own field: signup_activated, new and so ticked for everyone.
    Accounts still waiting for their sign-up code are the ones whose email isn't verified."""
    cr.execute("UPDATE res_users SET signup_activated = FALSE WHERE signup_email_verified = FALSE")
