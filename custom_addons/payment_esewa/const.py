# Part of Odoo. See LICENSE file for full copyright and licensing details.

# eSewa ePay v2 (https://developer.esewa.com.np/pages/Epay).
FORM_URLS = {
    'test': 'https://rc-epay.esewa.com.np/api/epay/main/v2/form',
    'enabled': 'https://epay.esewa.com.np/api/epay/main/v2/form',
}
STATUS_URLS = {
    'test': 'https://rc.esewa.com.np/api/epay/transaction/status/',
    'enabled': 'https://esewa.com.np/api/epay/transaction/status/',
}

# Public UAT merchant published by eSewa.
TEST_PRODUCT_CODE = 'EPAYTEST'
TEST_SECRET_KEY = '8gBm/:&EnhH.1/q'

REQUEST_SIGNED_FIELDS = ('total_amount', 'transaction_uuid', 'product_code')

# Transaction statuses returned by the status API / success redirect.
STATUS_MAPPING = {
    'done': ('COMPLETE',),
    'pending': ('PENDING', 'AMBIGUOUS'),
    'cancel': ('CANCELED', 'NOT_FOUND'),
    'error': ('FULL_REFUND', 'PARTIAL_REFUND'),
}

SUPPORTED_CURRENCIES = ['NPR']
DEFAULT_PAYMENT_METHOD_CODES = {'esewa'}
