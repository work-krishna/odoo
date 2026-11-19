# Part of Odoo. See LICENSE file for full copyright and licensing details.

import json
import logging
import re
import threading
import time
from collections import deque

import requests

from odoo.addons.delivery_ncm import const

_logger = logging.getLogger(__name__)

_throttle_lock = threading.Lock()
_recent_calls = deque(maxlen=const.MAX_REQUESTS_PER_SECOND)

# Connection failures that happen before anything reaches NCM: safe to retry.
_NOT_SENT_MARKERS = ('NewConnectionError', 'NameResolutionError', 'Failed to resolve', 'Connection refused')


class NcmError(Exception):
    """An NCM API call failed.

    `uncertain` is True when the request may have reached NCM (read timeout, dropped connection):
    for an order creation, NCM may then have created the order anyway.
    """

    def __init__(self, message, status_code=None, uncertain=False, payload=None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.uncertain = uncertain
        self.payload = payload

    def __str__(self):
        return self.message


def _throttle():
    """Keep this process under NCM's burst limit."""
    with _throttle_lock:
        if len(_recent_calls) == _recent_calls.maxlen:
            wait = 1.0 - (time.monotonic() - _recent_calls[0])
            if wait > 0:
                time.sleep(wait)
        _recent_calls.append(time.monotonic())


def _summarize_unexpected_body(text):
    """Return a short, safe hint from a non-JSON body (NCM's demo server answers errors with
    Django debug pages that also dump its settings, so never show the whole body)."""
    text = (text or '').strip()
    if not text:
        return ''
    if '<html' in text[:500].lower():
        title = re.search(r'<title>(.*?)</title>', text, re.S | re.I)
        value = re.search(r'<pre class="exception_value">(.*?)</pre>', text, re.S | re.I)
        parts = [m.group(1) for m in (title, value) if m]
        hint = ' '.join(' '.join(re.sub(r'<[^>]+>', ' ', p).split()) for p in parts)
    else:
        hint = ' '.join(line.strip() for line in text.splitlines()[:2] if line.strip())
    return hint[:300]


class NcmClient:
    """Thin wrapper around the NCM vendor API (documentation version 2026-05-28)."""

    def __init__(self, base_url, token=None, log=None):
        self.base_url = base_url.rstrip('/')
        self.token = token
        self.log = log  # callable(message, func_name) for the carrier's debug logging

    @staticmethod
    def _http(method, url, **kwargs):
        return requests.request(method, url, **kwargs)

    def _call(self, method, path, params=None, payload=None, timeout=const.TIMEOUT):
        url = f'{self.base_url}{path}'
        headers = {'Accept': 'application/json'}
        if self.token:
            headers['Authorization'] = f'Token {self.token}'
        if self.log:
            body = json.dumps(payload, ensure_ascii=False) if payload is not None else ''
            self.log(f'{method} {url} params={params or {}} body={body}', 'ncm_request')
        _throttle()
        try:
            response = self._http(method, url, headers=headers, params=params, json=payload, timeout=timeout)
        except requests.exceptions.ConnectTimeout as e:
            raise NcmError(f"Could not connect to NCM ({self.base_url}).") from e
        except requests.exceptions.ConnectionError as e:
            not_sent = any(marker in str(e) for marker in _NOT_SENT_MARKERS)
            raise NcmError(f"Lost the connection to NCM: {e}", uncertain=not not_sent) from e
        except requests.exceptions.Timeout as e:
            raise NcmError("NCM did not answer in time.", uncertain=True) from e
        except requests.exceptions.RequestException as e:
            raise NcmError(f"NCM request failed: {e}", uncertain=True) from e

        text = response.text or ''
        if self.log:
            self.log(f'HTTP {response.status_code} {text[:2000]}', 'ncm_response')
        try:
            data = json.loads(text) if text.strip() else {}
        except ValueError:
            data = None
        if response.status_code >= 400 or data is None:
            raise NcmError(
                self._error_message(response.status_code, data, text),
                status_code=response.status_code,
                payload=data,
            )
        return data

    @staticmethod
    def _error_message(status_code, data, text):
        if data is None:
            hint = _summarize_unexpected_body(text)
            message = f"NCM returned an unexpected response (HTTP {status_code})."
            return f"{message} {hint}" if hint else message
        if isinstance(data, dict):
            error = data.get('Error') or data.get('error') or data.get('errors')
            if isinstance(error, dict):
                return '; '.join(f'{key}: {value}' for key, value in error.items())
            if error:
                return str(error)
            for key in ('detail', 'message', 'Message'):
                if data.get(key):
                    return str(data[key])
        if status_code == 429:
            return "NCM's request limit was reached; try again later."
        return f"NCM rejected the request (HTTP {status_code})."

    @staticmethod
    def _as_list(data, what):
        if isinstance(data, dict) and data and set(data) <= {'detail', 'message'}:
            return []  # e.g. {"detail": "No comments found"}, sent with HTTP 200.
        if not isinstance(data, list):
            raise NcmError(f"NCM returned an unexpected {what} response.", payload=data)
        return data

    # Public endpoints ---------------------------------------------------------------------

    def get_branches(self):
        return self._as_list(self._call('GET', '/api/v2/branches'), 'branch list')

    def get_rate(self, from_branch, to_branch, rate_type):
        data = self._call('GET', '/api/v1/shipping-rate', params={
            'creation': from_branch,
            'destination': to_branch,
            'type': rate_type,
        })
        try:
            return float(data['charge'])
        except (KeyError, TypeError, ValueError) as e:
            raise NcmError("NCM returned no delivery charge.", payload=data) from e

    # Orders --------------------------------------------------------------------------------

    def create_order(self, values):
        data = self._call('POST', '/api/v1/order/create', payload=values, timeout=const.CREATE_TIMEOUT)
        order_id = data.get('orderid') if isinstance(data, dict) else None
        if not order_id:
            # A 2xx answer without an id: NCM may still have created the order.
            raise NcmError("NCM answered without an order number.", uncertain=True, payload=data)
        return int(order_id)

    def get_order(self, order_id):
        return self._call('GET', '/api/v1/order', params={'id': order_id})

    def get_order_statuses(self, order_id):
        return self._as_list(self._call('GET', '/api/v1/order/status', params={'id': order_id}), 'status')

    def get_order_comments(self, order_id):
        return self._as_list(self._call('GET', '/api/v1/order/comment', params={'id': order_id}), 'comment')

    def get_bulk_comments(self):
        return self._as_list(self._call('GET', '/api/v1/order/getbulkcomments'), 'comment')

    def get_statuses(self, order_ids):
        data = self._call('POST', '/api/v1/orders/statuses', payload={'orders': [int(i) for i in order_ids]})
        if not isinstance(data, dict):
            raise NcmError("NCM returned an unexpected status response.", payload=data)
        return data.get('result') or {}, data.get('errors') or []

    def post_comment(self, order_id, comment):
        return self._call('POST', '/api/v1/comment', payload={'orderid': str(order_id), 'comments': comment})

    # Vendor account ------------------------------------------------------------------------

    def get_assigned_branches(self):
        return self._as_list(self._call('GET', '/api/v2/vendor/assigned-branches'), 'assigned branch')

    def set_status_webhook(self, url):
        return self._call('POST', '/api/v2/vendor/webhook', payload={'webhook_url': url})

    def test_webhook(self, url):
        return self._call('POST', '/api/v2/vendor/webhook/test', payload={'webhook_url': url})
