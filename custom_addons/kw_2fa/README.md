# Forced Two-Factor Authentication (2FA)

[![License: LGPL-3](https://img.shields.io/badge/license-LGPL--3-blue.png)](http://www.gnu.org/licenses/lgpl-3.0-standalone.html)
[![Maintainer: Kitworks](https://img.shields.io/badge/maintainer-Kitworks-082567.png)](https://kitworks.systems/)

This module enforces two-factor authentication (2FA) for all users in Odoo. Users cannot log in without setting up TOTP authentication, and must enter a verification code on every login.

## Features

- **Mandatory 2FA**: All users (except admin) must configure TOTP to access the system
- **Automatic TOTP Setup**: Users without 2FA are redirected to QR code setup page
- **Universal Compatibility**: Works with Google Authenticator, Microsoft Authenticator, Authy, 1Password, Bitwarden, and any TOTP-compatible app
- **No Trusted Devices**: Verification code required on every login for maximum security
- **Admin Bypass**: System administrator (base.user_root) can optionally bypass 2FA

## How It Works

### First Login (TOTP Setup)

1. User enters login and password
2. System redirects to TOTP setup page with QR code
3. User scans QR code with authenticator app
4. User enters 6-digit verification code
5. TOTP is activated and user is logged in

### Subsequent Logins

1. User enters login and password
2. System prompts for TOTP verification code
3. User enters 6-digit code from authenticator app
4. User is logged in

## Installation

1. Install the module through the Odoo Apps menu
2. No additional configuration is required
3. All users will be required to set up 2FA on their next login

## Technical Details

- **TOTP Standard**: RFC 6238
- **Algorithm**: SHA1
- **Code Length**: 6 digits
- **Time Step**: 30 seconds
- **Secret Size**: 160 bits (20 bytes)
- **Dependencies**: `auth_totp`, `web`

### Modified Methods

| Model         | Method                        | Description                                    |
|---------------|-------------------------------|------------------------------------------------|
| `res.users`   | `_mfa_type()`                 | Returns 'totp' for all users (except admin)    |
| `res.users`   | `_mfa_url()`                  | Redirects to setup page if TOTP not configured |
| `res.users`   | `_kw_generate_totp_qr_data()` | Generates QR code and secret for TOTP setup    |
| `res.users`   | `_kw_totp_try_setting()`      | Validates and saves TOTP secret                |

- Override _mfa_type() to always return 'totp' for non-admin users
- Override _mfa_url() to redirect to setup page if TOTP not configured
- Add _kw_generate_totp_qr_data() for QR code generation
- Add _kw_totp_try_setting() for TOTP secret validation
- Use request.update_context(lang=user.lang) for user language support
- Use hasclass() instead of @class in xpath selectors

### Routes

| Route                 | Method   | Description                     |
|-----------------------|----------|---------------------------------|
| `/kw_2fa/setup_totp`  | GET      | TOTP setup page with QR code    |
| `/kw_2fa/enable_totp` | POST     | Validates code and enables TOTP |
| `/web/login/totp`     | GET/POST | TOTP verification on login      |

## Security Considerations

- TOTP secrets are stored securely in the database
- No "remember this device" option - code required every login
- Admin bypass can be disabled by modifying `_mfa_type()` method
- API access requires API keys when 2FA is enabled (password auth disabled)

## Compatibility

- **Odoo Version**: 18.0
- **Module Version**: 18.0.1.0.0
- **Category**: Security
- **License**: LGPL-3

## Bug Tracker

Bugs are tracked on [Kitworks Support](https://kitworks.systems/requests).
In case of trouble, please check there if your issue has already been reported.

## Maintainer

This module is maintained by [Kitworks Systems](https://kitworks.systems).

We can provide you further Odoo Support, Odoo implementation, Odoo customization, Odoo 3rd Party development and integration software, consulting services. Our main goal is to provide the best quality product for you.

For any questions [contact us](mailto:support@kitworks.systems).
