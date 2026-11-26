{
    'name': 'Sign-up Email Activation (OTP)',
    'version': '19.0.1.1.0',
    'summary': 'Website sign-ups activate their account with an emailed code or link before logging in',
    'description': """
People who create their own account on the website get a 6-digit code, by
email with an activation link and, where SMS codes are on, the same code by
SMS. Until they enter the code or open the link they cannot log in: every
login lands on the activation page, which can also send a new code. Code and
link expire after the time set in Settings (General Settings > Customer
Account). Invitations and password resets sent by email count as activation
too. Codes come from the one-time-code engine (auth_otp).
""",
    'category': 'Hidden/Tools',
    'author': 'EMI Platform',
    'license': 'LGPL-3',
    'depends': ['auth_signup', 'base_setup', 'auth_otp'],
    'data': [
        'data/mail_template_data.xml',
        'views/signup_verification_templates.xml',
        'views/res_config_settings_views.xml',
        'views/res_users_views.xml',
    ],
    'installable': True,
}
