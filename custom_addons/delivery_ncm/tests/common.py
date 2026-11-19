# Part of Odoo. See LICENSE file for full copyright and licensing details.

import json
from unittest.mock import patch
from urllib.parse import urlsplit

import requests

from odoo.fields import Command

from odoo.addons.delivery_ncm.models import delivery_carrier as carrier_module
from odoo.addons.sale.tests.common import SaleCommon

CLIENT_HTTP = 'odoo.addons.delivery_ncm.models.ncm_request.NcmClient._http'
THROTTLE = 'odoo.addons.delivery_ncm.models.ncm_request._throttle'

# Shaped like NCM's /api/v2/branches answer.
BRANCH_ROWS = [
    {
        'pk': 1, 'code': 'TINK1', 'name': 'TINKUNE', 'geocode': '27.68651234567, 85.34812345678',
        'address': 'Tinkune, Kathmandu', 'surcharge': '0.00', 'phone': '015199684',
        'branch_type': 'Branch', 'areas_covered': 'TINKUNE, KOTESHWOR, SUBIDHANAGAR',
        'phone2': '', 'province_name': 'BAGMATI', 'district_name': 'KATHMANDU',
    },
    {
        'pk': 2, 'code': 'NEWR1', 'name': 'NEW ROAD', 'geocode': '27.703, 85.311',
        'address': 'New Road, Kathmandu', 'surcharge': '0.00', 'phone': '9801000001',
        'branch_type': 'Branch', 'areas_covered': 'BAGBAZAR, ASAN, INDRACHOWK',
        'phone2': None, 'province_name': 'BAGMATI', 'district_name': 'KATHMANDU',
    },
    {
        'pk': 3, 'code': 'POKH1', 'name': 'POKHARA', 'geocode': '28.209, 83.985',
        'address': 'Pokhara', 'surcharge': '0.00', 'phone': '9801000002',
        'branch_type': 'Branch', 'areas_covered': 'LAKESIDE, BAGBAZAR,  Mahendrapul , LAKESIDE',
        'phone2': '', 'province_name': 'GANDAKI', 'district_name': 'KASKI',
    },
    {
        'pk': 4, 'code': 'SANK1', 'name': 'SANKHU', 'geocode': '',
        'address': 'Sankhu', 'surcharge': '50.00', 'phone': '9801000003',
        'branch_type': 'Logistics', 'areas_covered': None,
        'phone2': '', 'province_name': 'BAGMATI', 'district_name': 'KATHMANDU',
    },
]


def fake_response(status, data=None, text=None):
    response = requests.Response()
    response.status_code = status
    response.url = 'https://demo.nepalcanmove.com/api'
    if text is None:
        text = json.dumps(data)
        response.headers['Content-Type'] = 'application/json'
    response._content = text.encode()
    response.encoding = 'utf-8'
    return response


class FakeNcm:
    """Answers NcmClient's HTTP calls from canned routes and records every call."""

    def __init__(self):
        self.calls = []
        self.routes = {}

    def __call__(self, method, url, **kwargs):
        path = urlsplit(url).path
        self.calls.append({'method': method, 'path': path, 'url': url, **kwargs})
        handler = self.routes.get((method, path))
        if handler is None:
            raise AssertionError(f"Unexpected NCM call: {method} {path}")
        if isinstance(handler, Exception):
            raise handler
        return handler(kwargs) if callable(handler) else handler

    def calls_to(self, path, method=None):
        return [call for call in self.calls if call['path'] == path and (not method or call['method'] == method)]


class NcmCommon(SaleCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # The order-attempt log is written through a second cursor; in test mode that cursor
        # wraps the test transaction instead of committing for real (HttpCase already does this).
        if not cls._registry_patched:
            cls.registry_enter_test_mode_cls()
        cls.env['ncm.branch']._ncm_apply_branch_rows(BRANCH_ROWS)
        Branch = cls.env['ncm.branch']
        cls.branch_tinkune = Branch.search([('name', '=', 'TINKUNE')])
        cls.branch_newroad = Branch.search([('name', '=', 'NEW ROAD')])
        cls.branch_pokhara = Branch.search([('name', '=', 'POKHARA')])
        cls.area_lakeside = cls.env['ncm.area'].search([('name', '=', 'LAKESIDE')])

        cls.ncm = cls.env.ref('delivery_ncm.delivery_carrier_ncm')
        cls.ncm.write({
            'ncm_api_token': 'test-token',
            'ncm_from_branch_id': cls.branch_tinkune.id,
            'prod_environment': False,
            'ncm_delivery_type': 'Door2Door',
        })
        cls.customer = cls.env['res.partner'].create({
            'name': 'Sita Gurung',
            'phone': '+977 984-1234567',
            'street': 'Lakeside Road 6',
            'city': 'Pokhara',
            'ncm_area_id': cls.area_lakeside.id,
        })
        cls.phone_product = cls.env['product.product'].create({
            'name': 'Redmi 13 Pro+',
            'type': 'consu',
            'list_price': 25000.0,
            'weight': 0.4,
            'taxes_id': [Command.clear()],
        })
        cls.ncm.product_id.taxes_id = [Command.clear()]

    def setUp(self):
        super().setUp()
        carrier_module._rate_cache.clear()
        self.fake = FakeNcm()
        self.fake.routes[('GET', '/api/v1/shipping-rate')] = fake_response(200, {'charge': '150.00'})
        self.startPatcher(patch(CLIENT_HTTP, side_effect=self.fake))
        self.startPatcher(patch(THROTTLE))

    def _confirmed_order(self, quantity=1, partner=None):
        order = self.env['sale.order'].create({
            'partner_id': (partner or self.customer).id,
            'order_line': [Command.create({
                'product_id': self.phone_product.id,
                'product_uom_qty': quantity,
                'price_unit': 25000.0,
            })],
        })
        order.set_delivery_line(self.ncm, 150.0)
        order.action_confirm()
        return order

    def _route_created_order(self, order_id=747, delivery_charge='99.00'):
        self.fake.routes[('POST', '/api/v1/order/create')] = fake_response(
            200, {'Message': "Order Successfully Created", 'orderid': order_id},
        )
        self.fake.routes[('GET', '/api/v1/order')] = fake_response(200, {
            'orderid': order_id,
            'cod_charge': '25150.00',
            'delivery_charge': delivery_charge,
            'last_delivery_status': 'Pickup Order Created',
            'payment_status': 'Delivery Pending',
            'trackid': 'B79F9E65E673439',
        })

    @staticmethod
    def _validate(picking):
        for move in picking.move_ids:
            move.quantity = move.product_uom_qty
        picking.move_ids.picked = True
        return picking.button_validate()

    def _created_payload(self):
        calls = self.fake.calls_to('/api/v1/order/create')
        self.assertEqual(len(calls), 1, "Exactly one NCM order should have been created.")
        return calls[0]['json']
