# Part of Odoo. See LICENSE file for full copyright and licensing details.

# connectIPS gateway (NCHL), https://doc.connectips.com/docs/connectIPS-Gateway/merchant-interface
DEFAULT_BASE_URLS = {
    'test': 'https://uat.connectips.com',
    'enabled': 'https://login.connectips.com',
}
LOGIN_PAGE_ENDPOINT = '/connectipswebgw/loginpage'
VALIDATE_ENDPOINT = '/connectipswebws/api/creditor/validatetxn'

# Order matters: this is the signed token string.
LOGIN_TOKEN_FIELDS = (
    'MERCHANTID', 'APPID', 'APPNAME', 'TXNID', 'TXNDATE', 'TXNCRNCY', 'TXNAMT',
    'REFERENCEID', 'REMARKS', 'PARTICULARS',
)

SUPPORTED_CURRENCIES = ['NPR']
DEFAULT_PAYMENT_METHOD_CODES = {'connectips'}
