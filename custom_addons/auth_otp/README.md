# One-Time Codes (auth_otp)

One place for every one-time code on the site: sign-up activation, email login, SMS login, and the checkout and EMI phone checks.

- **One code per request.** It is generated here, stored only as a keyed hash, and delivered on every channel the flow allows and the person has. Sign-up sends the same code by email (with an activation link) and by SMS.
- **One set of rules:**
  - 10 minutes by default, or as the flow sets it;
  - 5 wrong tries;
  - 60 seconds before another code can be requested;
  - per hour, at most 5 codes per email address, 5 per phone number and 10 per public IP address;
  - a site-wide ceiling of 200 codes an hour (system parameter `auth_otp.max_per_hour`).
- **One log:** Settings > Technical > Security > One-Time Codes shows where each code went, whether it was used, and why a send failed.

Email delivery is built in: either the flow's own email or a generic one. SMS delivery comes from `sms_nestsms`.

## For developers

```python
result = env['auth.otp']._otp_issue('signup', user=user, email=user.email, phone=user.partner_id.phone,
                                    company=user.company_id, with_link=True, email_sender=sender)
# result: {'otp': record|False, 'error': message|False, 'channels': ['email', 'sms'], 'token': ...}
otp, error = env['auth.otp']._otp_verify('signup', code, user=user)
otp, error = env['auth.otp']._otp_verify_link('signup', token)
```

- Neither call raises: a refusal or a wrong guess is committed and keeps counting.
- `user`, else `email`, else `phone` identifies whose code it is, and each person has one live code per purpose.
- Flows adjust `_otp_policy(purpose, company)` (channels, validity).
- SMS modules implement `_otp_sms_available`, `_otp_send_sms`, `_otp_normalize_phone` and `_otp_sms_max_validity`.
