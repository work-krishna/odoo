# Part of Odoo. See LICENSE file for full copyright and licensing details.

# Khalti ePayment (KPG-2), https://docs.khalti.com/khalti-epayment/
API_URLS = {
    'test': 'https://dev.khalti.com/api/v2/',
    'enabled': 'https://khalti.com/api/v2/',
}
INITIATE_ENDPOINT = 'epayment/initiate/'
LOOKUP_ENDPOINT = 'epayment/lookup/'

# Lookup statuses. Only "Completed" means paid; Expired / User canceled come with HTTP 400.
STATUS_MAPPING = {
    'done': ('Completed',),
    'pending': ('Pending', 'Initiated'),
    'cancel': ('User canceled', 'Expired'),
    'error': ('Refunded', 'Partially refunded'),
}

SUPPORTED_CURRENCIES = ['NPR']
DEFAULT_PAYMENT_METHOD_CODES = {'khalti'}
