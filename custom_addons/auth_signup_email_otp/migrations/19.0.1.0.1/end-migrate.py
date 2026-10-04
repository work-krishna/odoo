from odoo import SUPERUSER_ID, api

# Fields that may have been changed since install (e.g. the sender, by mail_security_sender).
KEEP = ('subject', 'email_from', 'email_to', 'email_cc', 'reply_to', 'lang', 'auto_delete')


def migrate(cr, version):
    """The activation email got a new design. Its template is noupdate, so reload it from the
    data file to get the new body, and keep everything else as it was. This runs at the "end"
    stage: the kept sender may use fields of modules loaded after this one (mail_security_sender),
    and a template only accepts a sender it can render."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    template = env.ref('auth_signup_email_otp.mail_template_signup_verification', raise_if_not_found=False)
    if not template:
        return
    kept = {fname: template[fname] for fname in KEEP}
    template.reset_template()
    template.write(kept)
