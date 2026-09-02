# Part of Odoo. See LICENSE file for full copyright and licensing details.

# The base API URLs used depending on the provider's state.
# These are Fonepay's published UAT and Production merchant API hosts as used in their official
# integration samples. Confirm these with Fonepay support if your merchant account was given a
# different host.
API_URLS = {
    'test': 'https://uat-new-merchant-api.fonepay.com',
    'enabled': 'https://uat-new-merchant-api.fonepay.com',
}

# Endpoints of the Fonepay Dynamic QR API, relative to the base API URL.
QR_REQUEST_ENDPOINT = '/api/merchant/merchantDetailsForThirdParty/thirdPartyDynamicQrDownload'
QR_STATUS_ENDPOINT = '/api/merchant/merchantDetailsForThirdParty/thirdPartyDynamicQrGetStatus'

# The currencies supported by Fonepay, in ISO 4217 format.
SUPPORTED_CURRENCIES = ['NPR']

# The codes of the payment methods to activate when Fonepay is activated.
DEFAULT_PAYMENT_METHOD_CODES = {'fonepay'}
