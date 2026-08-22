{
    "name": "Email OTP Login Authentication",
    "version": "19.0.1.0.0",
    "category": "Website/Authentication",
    "summary": "Secure passwordless login using Email OTP verification",
    "description": """
Email OTP Login Authentication

This module allows users to securely log in to Odoo using a One-Time Password (OTP)
sent to their email address. It eliminates the need for traditional passwords and
provides a seamless authentication experience.

## Main Features:

* Passwordless login via Email OTP
* Secure 6-digit OTP generation
* Automatic Portal User creation
* OTP expiration validation
* Resend OTP functionality
* Responsive OTP verification popup
* Login page integration
* Reset password page integration
* Automatic user authentication after OTP verification
* Compatible with Community and Enterprise editions

## Benefits:

* Improved security
* Better user experience
* Reduced password reset requests
* Faster user onboarding
* Modern authentication workflow

## Perfect for:

* Customer Portals
* Donation Websites
* Membership Platforms
* Event Registration Portals
* Public Website Users
  """,
    "author": "i8CLOUD Consulting",
    "company": "i8CLOUD Consulting",
    "maintainer": "i8CLOUD Consulting",
    "website": "https://www.i8cloudconsulting.com",
    "support": "contact@i8cloudconsulting.com",
    'license': 'LGPL-3',
    'price': 0.00,
    'currency': 'USD',
    "depends": [
        "base",
        "mail",
        "website"
    ],
    "data": [
        "data/mail_template_data.xml",
        "views/templates.xml",
        "views/login_templates.xml"
    ],
    "assets": {
        "web.assets_frontend": [
            "i8_otp_login/static/src/css/otp.css",
            "i8_otp_login/static/src/js/otp_login.js"
        ]
    },
    "images": ["static/description/banner.gif", "static/description/icon.png"],

    "installable": True,
    "application": True,
    "auto_install": False
}
