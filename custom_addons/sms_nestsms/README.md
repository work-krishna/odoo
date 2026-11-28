# NestSMS

Sends every SMS Odoo sends through [NestSMS](https://nestsms.com), on Nepal's domestic routes only. It also adds customer texts and one-time codes (OTPs), each switched on separately.

## What it adds

Installing `sms_nestsms` brings in each module below whose app is installed.

**Texts to customers**

| Module | Texts the customer when… | Switch |
|---|---|---|
| `sms_nestsms_sale` | their order is confirmed | Settings > General Settings > Send SMS |
| `sms_nestsms_payment` | their payment is confirmed: online gateways, EMI down payments and instalments, and payments registered by hand | Settings > General Settings > Send SMS |
| `sms_nestsms_stock` | a delivery is validated ("Your order S00123 has been shipped."). This replaces core `stock_sms`'s wording, whose "n°" character made every text Unicode. | Inventory > Configuration > Settings > SMS Confirmation |
| `sms_nestsms_ncm` | Nepal Can Move sends the parcel out for delivery (with the cash to keep ready, for cash on delivery), and when it is delivered | the NCM delivery method > Text Customers |

**One-time codes**

Each flow needs its own approved NestSMS OTP template, and is switched on in Settings > General Settings > Send SMS.

| Module | Flow |
|---|---|
| `sms_nestsms_login` | Customers log in with a code texted to their **verified** number. The login page shows a "Log in with an SMS code" link. Staff accounts can't log in this way: they keep their password and two-factor authentication. |
| `sms_nestsms_signup` | Website sign-ups enter their mobile number and get **one activation code by email and a different one by SMS**. Either activates the account and closes the other, and the activation page names both destinations. The SMS code proves the mobile number (the website then reminds them to confirm their email); the email code proves the email (checkout then confirms the mobile). A number outside Nepal, or a failed SMS, still leaves the email. Builds on `auth_signup_email_otp`. |
| `sms_nestsms_website_sale` | Strict when switched on: after the address step the buyer proves their own mobile number (typed on the page, apart from the addresses) before choosing delivery and paying. A number proven once, at sign-up or on an earlier order, counts; delivery addresses may carry any number. The cart check behind every payment path (shop payment, free orders, the quotation payment route) refuses carts without a proven number, and checkout is held rather than skipped while no approved template is set. The order form shows the customer's verified mobile. |
| `sms_nestsms_emi` | EMI applicants confirm their number before the form. The application always carries the proven number, whatever the form sends. |
| `sms_nestsms_reset_password` | Forgot password: the customer picks email or SMS. SMS sends a code to the account's **verified** mobile number and a different code by email (either works, the log records which). The verified number also finds the account. Staff accounts and unproven numbers never get a reset SMS. Builds on `auth_signup_email_otp`, which handles the email-only reset. |
| `sms_nestsms_portal` | My Account shows Verified / Not verified under the email and the phone, with a Verify button: the email goes to `/my/verify-email`, the phone to `/my/verify-phone` (an SMS code to the number on the account). A customer who changes their email address has to confirm the new one. |

**One code engine.** Every code on the site comes from `auth_otp` (the One-Time Codes module): sign-up, email login, SMS login, checkout and EMI. It generates the codes (one per channel), stores only keyed hashes, and enforces the expiry, the tries and the rate limits in one place. This module is the SMS channel.

A number proven by an SMS code (sign-up, checkout, EMI application) is stored on the contact as **Phone Verified by SMS**, and checkout doesn't ask for it again. Login by SMS only works for verified numbers: otherwise a typo in a customer's phone number would let a stranger who owns that number into their account.

## Setup

1. In the NestSMS dashboard, go to API Integration > API Token > Add Token, and give the key the `sms:*` permission (send, status, balance, templates). Copy the key: it is shown only once. If the key has an IP whitelist, add the Odoo server's IP address.
2. In Odoo, go to Settings > General Settings > Send SMS:
   - Paste the key into **NestSMS API Key**.
   - Fill in **Brand Name**: one word with no spaces, such as `Flagship-Store`. Texts start with it, followed by a colon. It must match your OTP templates.
   - Click **Send a test SMS**, then **Check balance**.
3. For each OTP flow:
   1. Have the template approved in NestSMS, with message type OTP. Example: `Flagship-Store: Your OTP for login is {otp}. It is valid for 10 minutes. Never share this code with anyone.`
   2. Tick the flow's box and click **Choose…**. Odoo lists your NestSMS templates of type OTP:
      - each shows its name, an **Approved** or **Waiting for approval** badge, its text in small print, and a warning if it doesn't start with the brand name and a colon;
      - usable ones come first;
      - **Use this template** fills in the ID and checks it straight away.

      You can also paste an ID and click **Check**. Either way, Odoo confirms the template is approved, has the OTP type, has a placeholder for the code, uses only placeholders Odoo can fill, and, once filled in, starts with the brand name and a colon and says 10 minutes.

      Placeholders Odoo fills (NestSMS requires every one a template declares):

      | Placeholder | Filled with |
      |---|---|
      | `{otp}`, `{code}`, `{pin}` | the code |
      | `{companyName}`, `{app_name}`, `{brand}`, `{appName}`… | the Brand Name above, e.g. `FlagshipStore` |
      | `{expiry}`, `{validity}`, `{minutes}`… | `10`, or `10 minutes` when the text doesn't already say "minutes" |
      | `{purpose}` | login / account registration / order confirmation / EMI application |

      So `{companyName}: Your OTP for {purpose} is {otp}. It is valid for {expiry} minutes.` works. Any other placeholder (a customer name, say) blocks the template.
   3. **Codes stay off until that check passes.** The row then says "Approved by NestSMS: codes are on". Editing the template ID switches codes off again until it is checked once more.

   If Choose… shows `IP_RESTRICTED`, the API key only works from whitelisted addresses. The message shows the address NestSMS sees: add it to the key's whitelist in NestSMS.

Each company has its own key, brand name and templates. Nothing is sent for a company until it has a key.

The key is kept in the database, readable only by administrators. It is never in the source code (this repository is public). It is cleared when a database is neutralized, so a copied database can't text customers or spend the wallet.

## Rules this module enforces

NestSMS accounts are bound by Nepal Telecommunications Authority (NTA) rules. Breaking them can bring fines or a suspended account.

- **Domestic routes only.** Nothing falls back to Odoo's own SMS service (IAP) or to Twilio, because both route abroad. Twilio can't be installed next to this module. Numbers that aren't Nepali mobiles (96/97/98 followed by 8 digits) are refused.
- **OTPs only through approved templates.** Codes are sent only as `template_id` plus `{otp}`, and only with a template that Check confirmed as approved. Plain text that reads like a code is refused before it reaches NestSMS.
- **No repeated attempts with a bad template.** NestSMS says repeated attempts to get around template approval can cost the account its OTP service. If NestSMS rejects a flow's template while sending (not found, wrong type, missing variables...), that flow switches itself off at once and logs an error. It stays off until an administrator fixes the template and clicks Check. While off, customers aren't blocked: login falls back to the password, sign-up to email, and checkout and EMI applications go ahead without the code.
- **Fair sending.**
  - Each event texts the customer once.
  - Numbers on the phone blacklist (opt-outs) get no customer texts.
  - Texts are transactional only.
  - If an error would hit every message (bad key, empty wallet, rate limit, NestSMS down), sending stops instead of retrying in a loop.
- **No waiting on NestSMS.** Customer texts are queued and sent right after the order, payment or status change is saved.

One-time codes:

- Codes are 6 digits, valid 10 minutes, and only a keyed hash is stored.
- A code stops working after 5 wrong tries.
- After a code is sent, another can be requested after 60 seconds.
- At most 5 codes go to one number per hour, and at most 10 to one IP address per hour.
- A site-wide ceiling of 200 codes per hour stops bots draining the wallet. It is set by the system parameter `auth_otp.max_per_hour`.
- Every code request is listed under Settings > Technical > Security > One-Time Codes, with where it went (email, SMS) and why a send failed.

The per-IP limit needs the real visitor address. Behind a reverse proxy, start Odoo with `proxy_mode = True` and have the proxy send `X-Forwarded-For`. Otherwise every visitor shows the proxy's private address, the per-IP limit is skipped, and only the per-number limits and the site-wide ceiling apply.

## Daily use

- Each customer text appears on the chatter of its order, payment or delivery. A cron asks NestSMS every 15 minutes and marks each text **Delivered** or **Failed**, for 2 days after sending. A red SMS icon means it failed: hover over it to see the reason, and use **Resend** once the cause is fixed.
- To change a customer text, go to Settings > Technical > SMS Templates. Keep to plain characters: "Rs." rather than the rupee sign. Text in Nepali script goes out as Unicode, which fits 70 characters per credit instead of 160.

## Troubleshooting

| Failure shown on the chatter | Cause |
|---|---|
| Unregistered Account | Missing, wrong, expired or IP-restricted API key, or the sender ID isn't approved. The reason gives NestSMS's code. |
| Insufficient Credit | The NestSMS wallet needs a top-up. |
| Country Not Supported | The number isn't a Nepali mobile. |
| Country-specific Registration Required | The text looked like an OTP, or a template problem. |
| Server Error | NestSMS was unreachable, failed, or rate-limited the key. Resend later. |
| Not Delivered | NestSMS reported the handset unreachable. The reason gives their message. |

If customers report that codes don't arrive, check the code log (One-Time Codes): the **Not Sent** rows, and the failure reason on rows that only reached one channel, give NestSMS's reason.


## Known limits

- When checkout verification is on, express checkout (wallet buttons on the cart) can't pay until the shopper has confirmed their number.
- Delivery status is checked for 2 days after sending. After that, a text stays "Sent".

## Developer notes

- `tools/sms_api.py` is the only file that talks to NestSMS. Everything goes through `SmsApiNestSms._nestsms_request`, which the tests replace (`tests/common.py: patch_nestsms`).
- Core `sms.sms._split_by_api` sends the queue through Odoo IAP whatever the company has chosen. `models/sms_sms.py` overrides it to route each company's SMS through NestSMS.
- Errors map only to failure types that `sms.sms`, `mail.notification` and `mailing.trace` all accept, so recording a failure can't crash. A test checks this.
- Customer texts: call `record._sms_nestsms_notify(template_or_xmlid, partner)`. It queues the SMS, logs it on the chatter, and returns False when it skips.
- One-time codes:
  - Issue with `env['auth.otp']._otp_issue(purpose, user=..., email=..., phone=..., company=..., with_link=False, email_sender=None)` and check with `_otp_verify(purpose, code, user=/email=/phone=)` (auth_otp).
  - This module plugs into that engine as the SMS channel through `_otp_sms_available`, `_otp_send_sms`, `_otp_normalize_phone` (Nepali mobiles only) and `_otp_sms_max_validity` (10 minutes, as the approved template text says). Login, checkout and EMI are SMS-only purposes (`SMS_ONLY_PURPOSES`).
  - Both return `(record, False)` or `(False, message)` and never raise, so a wrong guess stays counted even when the caller shows an error.
  - Mark a proven number with `partner._sms_mark_phone_verified(number)`.
  - Purposes and their company fields (`sms_otp_<purpose>`, `sms_otp_<purpose>_template`) live in this module. Each flow module only adds its own row in Settings.
  - Approval is kept in the system parameter `sms_nestsms.otp_approved.<company id>.<purpose>`, holding the approved template ID. It is not a stored field, so deploying needs no module upgrade first. `company._sms_otp_enabled(purpose)` is the single gate.
- `OTP_VALIDITY` (10 minutes) must match the approved template text. Check flags any mismatch.
- Default texts stay within the GSM-7 alphabet (`is_gsm7`, checked by the tests).
- Tests: `--test-tags /sms_nestsms,/sms_nestsms_sale,/sms_nestsms_payment,/sms_nestsms_stock,/sms_nestsms_ncm,/sms_nestsms_signup,/sms_nestsms_login,/sms_nestsms_website_sale,/sms_nestsms_emi,/sms_nestsms_reset_password,/sms_nestsms_portal`.

## Get template-ID:
Request:
```
curl -s -H "X-API-Key: nsms_..." "https://auth.nestsms.com/api/v1/sms/templates"
```
Response:
```json
{
   "success":true,
   "message":"Templates fetched successfully",
   "data":{
      "templates":[
         {
            "id":"c8ab07bd-a10c-442f-b278-2c4cf4f2685b",
            "organizationId":"a217df7a-36d4-4be5-a78e-5d71d6c9623e",
            "name":"OTP",
            "messageType":"OTP",
            "encoding":"GSM_7",
            "content":"{companyName}: Your OTP is {otp}. Valid for {expiry} minutes. Do not share this code with anyone.",
            "variables":[
               "companyName",
               "otp",
               "expiry"
            ],
            "usageCount":0,
            "isActive":true,
            "isVerified":true,
            "verifiedAt":"2026-11-26T11:11:28.813Z",
            "verifiedBy":"d9374296-7647-4312-bc23-b1f6b3254060",
            "rejectionReason":null,
            "activatedAt":"2026-11-26T11:11:28.813Z",
            "createdAt":"2026-11-26T10:51:59.613Z",
            "updatedAt":"2026-11-26T11:11:28.814Z",
            "deletedAt":null
         }
      ],
      "pagination":{
         "nextCursor":null,
         "hasNextPage":false,
         "limit":30
      }
   }
}
```