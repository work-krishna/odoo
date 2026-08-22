{
    'name': 'Forced Two-Factor Authentication (2FA)',
    'summary': (
        'Two-Factor Authentication | 2FA | TOTP | Forced 2FA | Mandatory 2FA '
        '| OTP Authentication | Time-based OTP | Authenticator App | Google '
        'Authenticator | Microsoft Authenticator | Authy | Login Security | '
        'Account Security | User Authentication | Compliance | Strong '
        'Authentication. Forces every user to enable TOTP two-factor '
        'authentication on first login. Blocks system access until 2FA is '
        'configured.'
    ),

    'author': 'Kitworks Systems',
    'website': 'https://kitworks.systems/',

    'category': 'Authentication',
    'license': 'LGPL-3',
    'version': '19.0.1.0.1',

    'depends': [
        'auth_totp',
        'web',
    ],

    'external_dependencies': {
        'python': [],
    },

    'data': [
        'views/templates_for_2fa.xml',
    ],
    'demo': [
    ],

    'assets': {
        'kw_2fa.kw_2fa_assets': [
            'kw_2fa/static/src/css/kw_style.css',
        ],
    },

    'installable': True,
    'auto_install': False,
    'application': False,
    'images': [
        'static/description/cover.png',
        'static/description/icon.png',
        'static/description/screenshot.png',
    ],

}
