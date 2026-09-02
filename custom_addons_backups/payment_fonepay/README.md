# Payment Provider: Fonepay

Adds **Fonepay** (Nepal) as a payment provider, using Fonepay's Merchant Integration through
Device for Dynamic QR (v1.2, July 2025).

## How it works

Fonepay's dynamic QR flow does not fit Odoo's usual "redirect to the provider" pattern: instead
of sending the customer to an external checkout page, the merchant asks Fonepay for a QR code and
displays it itself, then finds out whether the customer paid.

1. When the customer confirms the payment, Odoo calls Fonepay's **QR Request** API
   (`thirdPartyDynamicQrDownload`) with the order amount and gets back a `qrMessage` string.
2. The customer lands on Odoo's payment status page (`/payment/status`), where that string is
   rendered as a QR code image (via the `qrcode` Python library) for them to scan with their
   mobile banking or wallet app.
3. Fonepay's documented way of notifying the merchant is a **WebSocket** connection, which isn't a
   good fit for Odoo's multi-worker, request/response architecture. Instead, this module polls
   Fonepay's **Check QR Request Status** API (`thirdPartyDynamicQrGetStatus`) from the customer's
   browser (every few seconds, via `/payment/fonepay/poll`) until the payment is confirmed.
4. Once Fonepay reports `paymentStatus: success`, the transaction is marked `done` and Odoo's
   standard post-processing (invoice/order confirmation, etc.) takes over as usual.

No inbound webhook or public callback URL is required on your side.

## Setup

In **Accounting/Website → Payment Providers → Fonepay**, fill in:

- **Merchant Code**, **Username**, **Password**: provided by Fonepay.
- **Secret Key**: found on your Fonepay merchant profile page after logging in. It is used to
  compute the `HMAC_SHA512` "Data Validation" signature Fonepay requires on every request; it
  never leaves the server.

Set the provider to **Test Mode** first and use Fonepay's published sandbox credentials to confirm
everything works end-to-end before switching it to **Enabled**:

```
merchant code: fonepay123
secret key:    fonepay
username:      bijayk
password:      password
```


Fonepay only settles in **NPR**, so the provider is automatically hidden at checkout for orders in
any other currency.

## Things to double-check before going live

- **API host**: the technical document only gives placeholders (`{Base_URL_API}`) for Fonepay's
  API host. This module defaults to Fonepay's commonly published UAT
  (`dev-merchantapi.fonepay.com`) and Production (`merchantapi.fonepay.com`) hosts, selected
  automatically from the provider's Test/Enabled state — confirm these with Fonepay support if
  your merchant account was issued a different host.
- **"Pending" vs. "failed"**: Fonepay's own documentation shows the exact same example payload for
  the status check's "Pending" and "Failed" responses. Because of that ambiguity, this module only
  ever moves a transaction to `done` on an explicit `paymentStatus: success`; any other value
  leaves the transaction `pending` rather than risk canceling a payment that actually went through
  a moment later. Adjust `PaymentTransaction._apply_updates` if your own testing shows Fonepay
  reliably distinguishes the two.
- The `qrcode` Python package (already part of Odoo's standard `requirements.txt`) must be
  installed in the environment running Odoo.
