{
    'name': 'Sign-up Email Activation (OTP)',
    'version': '19.0.1.3.0',
    'summary': 'Website sign-ups activate their account, and forgotten passwords are reset, with a code sent by email (and SMS)',
    'description': """
People who create their own account on the website get a 6-digit code by
email, with an activation link, and, where SMS codes are on, a different code
by SMS. Until they enter one of them or open the link they cannot log in:
every login lands on the activation page, which can also send new codes.
Entering either code closes both.

The code used says what is proven. The email code or link proves the email
address; the SMS code proves the mobile number, and the website then reminds
the person to confirm their email address too, without blocking anything.

Codes and link expire after the time set in Settings (General Settings >
Customer Account). Invitations and password resets sent by email count as
activation too. Codes come from the one-time-code engine (auth_otp).

A forgotten password is reset with a code too: by email or, where SMS codes
are on for password resets (sms_nestsms_reset_password), by SMS to the
account's verified mobile number plus a different code by email. The page
answers the same whether or not an account matches. Emailed reset and
invitation links keep working.

Changing the email address of a customer account makes it unconfirmed again
until the new address is confirmed.
""",
    'category': 'Hidden/Tools',
    'author': 'EMI Platform',
    'license': 'LGPL-3',
    'depends': ['auth_signup', 'base_setup', 'auth_otp'],
    'data': [
        'data/mail_template_data.xml',
        'views/signup_verification_templates.xml',
        'views/reset_password_templates.xml',
        'views/res_config_settings_views.xml',
        'views/res_users_views.xml',
    ],
    'installable': True,
}
