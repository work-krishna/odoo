# Part of Odoo. See LICENSE file for full copyright and licensing details.

API_URLS = {
    'demo': 'https://demo.nepalcanmove.com',
    'production': 'https://portal.nepalcanmove.com',
}

# The branch list is public. Production has the complete list (649 branches in Nov 2026); the
# demo server only knows a handful, so branches are always synced from production.
BRANCH_SOURCE_ENVIRONMENT = 'production'

# NCM allows 3 requests per second per vendor (burst throttle seen on the demo server).
MAX_REQUESTS_PER_SECOND = 3
TIMEOUT = (5, 20)  # (connect, read) seconds
CREATE_TIMEOUT = (5, 30)

RATE_CACHE_SECONDS = 24 * 3600
STATUS_BATCH_SIZE = 100  # NCM recommends at most 100 ids per bulk request.
STATUS_SYNC_MAX_AGE_DAYS = 90
WEBHOOK_EVENT_GIVE_UP_HOURS = 2

DELIVERY_TYPES = [
    ('Door2Door', "Door to door: NCM picks up and delivers"),
    ('Branch2Door', "Branch to door: we drop at the branch, NCM delivers"),
    ('Door2Branch', "Door to branch: NCM picks up, customer collects"),
    ('Branch2Branch', "Branch to branch: we drop, customer collects"),
]

# `type` parameter of /api/v1/shipping-rate for each order `delivery_type`.
RATE_TYPES = {
    'Door2Door': 'Pickup/Collect',
    'Branch2Door': 'Send',
    'Door2Branch': 'D2B',
    'Branch2Branch': 'B2B',
}

COLLECT_AT_BRANCH_TYPES = ('Door2Branch', 'Branch2Branch')

NCM_STATES = [
    ('created', "Order created"),
    ('pickup', "Sent for pickup"),
    ('picked_up', "Picked up"),
    ('in_transit', "In transit"),
    ('out_for_delivery', "Out for delivery"),
    ('delivered', "Delivered"),
    ('returning', "Returning"),
    ('returned', "Returned to us"),
    ('cancel_requested', "Cancellation requested"),
    ('cancelled', "Cancelled"),
    ('exception', "Needs attention"),
    ('unknown', "Other"),
]

FINAL_STATES = ('delivered', 'returned', 'cancelled')

# NCM status strings, lower-cased, mapped to our states. NCM has not published the full list
# (asked in our questions to NCM), so `status_to_state` falls back to keywords.
STATUS_MAP = {
    'pickup order created': 'created',
    'drop off order created': 'created',
    'order created': 'created',
    'sent for pickup': 'pickup',
    'pickup complete': 'picked_up',
    'dispatched': 'in_transit',
    'in transit': 'in_transit',
    'arrived': 'in_transit',
    'sent for delivery': 'out_for_delivery',
    'delivered': 'delivered',
    'sent to vendor': 'returned',
    'returned to vendor': 'returned',
    'returned': 'returned',
    'cancelled': 'cancelled',
    'canceled': 'cancelled',
}


def status_to_state(status):
    """Map an NCM status string to one of `NCM_STATES`."""
    key = ' '.join((status or '').lower().split())
    if not key:
        return 'unknown'
    if key in STATUS_MAP:
        return STATUS_MAP[key]
    if 'cancel' in key:
        return 'cancelled'
    if 'return' in key:
        return 'returning'
    if any(word in key for word in ('hold', 'fail', 'undeliver', 'not received', 'refused')):
        return 'exception'
    if 'sent for delivery' in key or 'out for delivery' in key:
        return 'out_for_delivery'
    if any(word in key for word in ('transit', 'arrived', 'dispatch')):
        return 'in_transit'
    if 'pickup' in key:
        return 'pickup'
    return 'unknown'
