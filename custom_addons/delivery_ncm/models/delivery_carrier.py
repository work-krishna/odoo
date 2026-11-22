# Part of Odoo. See LICENSE file for full copyright and licensing details.

import json
import logging
import math
import secrets
import time
from collections import defaultdict
from datetime import timedelta

from markupsafe import Markup

from odoo import _, api, fields, models, SUPERUSER_ID
from odoo.exceptions import UserError

from odoo.addons.delivery_ncm import const
from odoo.addons.delivery_ncm.models.ncm_branch import normalize_name
from odoo.addons.delivery_ncm.models.ncm_request import NcmClient, NcmError

_logger = logging.getLogger(__name__)

# (environment, from branch, to branch, rate type) -> (price in NPR, expiry as time.monotonic())
_rate_cache = {}


def extract_order_id(payload):
    """Find NCM's order id in a webhook payload (NCM has only documented its test payload)."""
    if not isinstance(payload, dict):
        return 0
    for source in (payload, payload.get('data') if isinstance(payload.get('data'), dict) else {}):
        for key in ('order_id', 'orderid', 'orderId', 'order', 'pk'):
            try:
                value = int(str(source.get(key)).strip())
            except (TypeError, ValueError):
                continue
            if value > 0:
                return value
    return 0


class DeliveryCarrier(models.Model):
    _inherit = 'delivery.carrier'

    delivery_type = fields.Selection(
        selection_add=[('ncm', "Nepal Can Move")],
        ondelete={'ncm': lambda recs: recs.write({'delivery_type': 'fixed', 'fixed_price': 0})},
    )
    ncm_api_token = fields.Char(
        string="NCM API Token", groups='base.group_system', copy=False,
        help="From the NCM vendor portal's API page. Use the demo token while this method is in test mode.",
    )
    ncm_from_branch_id = fields.Many2one(
        'ncm.branch', string="Default Pickup Branch",
        help="The NCM branch parcels leave from, unless the product (or its warehouse) sets its own "
             "NCM pickup branch. Pickup branches must be ones NCM assigned to your account "
             "('Check account' lists them).",
    )
    ncm_delivery_type = fields.Selection(const.DELIVERY_TYPES, string="NCM Service", default='Door2Door')
    # Read by Odoo's checkout and quotation wizard as `<delivery_type>_use_locations`.
    ncm_use_locations = fields.Boolean(compute='_compute_ncm_use_locations')
    ncm_notify_customer = fields.Boolean(
        string="Email Customers",
        help="Email the customer when NCM sends the parcel out for delivery, and when it is delivered.",
    )
    ncm_extra_kg_price = fields.Float(
        string="Extra Charge per kg",
        help="Added to NCM's quote for each kg above 1 kg. NCM's rate API ignores weight, so use "
             "this until NCM confirms how weight is charged.",
    )
    ncm_webhook_secret = fields.Char(
        groups='base.group_system', copy=False, default=lambda self: secrets.token_urlsafe(24),
    )
    ncm_webhook_url = fields.Char(
        string="Webhook URL", compute='_compute_ncm_webhook_url', groups='base.group_system',
        help="Paste this address in both webhook fields of the NCM vendor portal's API page.",
    )

    @api.depends('delivery_type', 'ncm_delivery_type')
    def _compute_ncm_use_locations(self):
        for carrier in self:
            carrier.ncm_use_locations = (
                carrier.delivery_type == 'ncm' and carrier.ncm_delivery_type in const.COLLECT_AT_BRANCH_TYPES
            )

    def _compute_ncm_webhook_url(self):
        for carrier in self:
            secret = carrier.sudo().ncm_webhook_secret
            carrier.ncm_webhook_url = (
                f"{carrier.get_base_url()}/delivery_ncm/webhook/{secret}"
                if carrier.delivery_type == 'ncm' and secret else False
            )

    # Helpers -------------------------------------------------------------------------------

    def _ncm_environment(self):
        self.ensure_one()
        return 'production' if self.prod_environment else 'demo'

    def _ncm_client(self, require_token=True):
        self.ensure_one()
        token = self.sudo().ncm_api_token
        if require_token and not token:
            raise UserError(_("Add the NCM API token on the delivery method %s.", self.name))
        return NcmClient(const.API_URLS[self._ncm_environment()], token=token, log=self.log_xml)

    def _ncm_npr(self):
        return self.env.ref('base.NPR')

    def _ncm_to_kg(self, weight):
        uom = self.env['product.template']._get_weight_uom_id_from_ir_config_parameter()
        kg = self.env.ref('uom.product_uom_kgm')
        return uom._compute_quantity(weight, kg) if weight and uom != kg else (weight or 0.0)

    def _ncm_extra_weight_charge(self, weight_kg):
        self.ensure_one()
        if not self.ncm_extra_kg_price or weight_kg <= 1:
            return 0.0
        return math.ceil(round(weight_kg - 1, 3)) * self.ncm_extra_kg_price

    def _ncm_pickup_branch_for(self, product, warehouse=None):
        """The NCM branch `product` leaves from: the product's own, else its warehouse's, else
        this delivery method's default."""
        self.ensure_one()
        candidates = (
            product.ncm_pickup_branch_id,
            warehouse.ncm_pickup_branch_id if warehouse else None,
            self.ncm_from_branch_id,
        )
        return next((branch for branch in candidates if branch and branch.active), self.env['ncm.branch'])

    @api.model
    def _ncm_goods_lines(self, order):
        return order.order_line.filtered(
            lambda line: not line.is_delivery and not line.display_type and line.product_id.type == 'consu'
        )

    def _ncm_is_ready_for_order(self, order):
        """Whether this method can ship `order`: an API token, and a pickup branch for each product."""
        self.ensure_one()
        if self.delivery_type != 'ncm':
            return True
        return bool(self.sudo().ncm_api_token) and all(
            self._ncm_pickup_branch_for(line.product_id, order.warehouse_id)
            for line in self._ncm_goods_lines(order)
        )

    def _ncm_rate_groups(self, order):
        """NCM's charge (NPR) for each parcel of `order`: one per pickup branch its goods leave from.

        :return: list of (pickup branch, charge) tuples
        :raise UserError: when a product has no pickup branch, or the destination is unknown
        :raise NcmError: when NCM cannot quote
        """
        self.ensure_one()
        weights = {}
        missing = []
        for line in self._ncm_goods_lines(order):
            product = line.product_id
            branch = self._ncm_pickup_branch_for(product, order.warehouse_id)
            if not branch:
                missing.append(product.display_name)
                continue
            quantity = line.product_uom_id._compute_quantity(line.product_uom_qty, product.uom_id)
            weights[branch] = weights.get(branch, 0.0) + self._ncm_to_kg(product.weight * quantity)
        if missing:
            raise UserError(_(
                "No NCM pickup branch for %(products)s: set one on the product, or a default pickup "
                "branch on the delivery method %(method)s.",
                products=', '.join(missing), method=self.name,
            ))
        destination = order._ncm_get_dest_branch(carrier=self)
        groups = []
        for branch, weight in weights.items():
            # Checkout needs a price before the customer can open the branch selector: quote the
            # pickup branch's own city until a branch is chosen (the order is then re-priced).
            to_branch = destination or (branch if self.ncm_use_locations else destination)
            if not to_branch:
                raise UserError(_(
                    "Choose the NCM delivery area of the shipping address, so we know which NCM branch "
                    "delivers there."
                ))
            groups.append((branch, self._ncm_get_rate(branch, to_branch) + self._ncm_extra_weight_charge(weight)))
        return groups

    def _ncm_get_rate(self, from_branch, to_branch):
        """NCM's delivery charge in NPR from `from_branch` to `to_branch`, cached for a day."""
        self.ensure_one()
        key = (
            self._ncm_environment(),
            from_branch.name,
            to_branch.name,
            const.RATE_TYPES[self.ncm_delivery_type or 'Door2Door'],
        )
        cached = _rate_cache.get(key)
        if cached and cached[1] > time.monotonic():
            return cached[0]
        price = self._ncm_client(require_token=False).get_rate(*key[1:])
        _rate_cache[key] = (price, time.monotonic() + const.RATE_CACHE_SECONDS)
        return price

    @api.model
    def _ncm_rate_error(self, message):
        return {'success': False, 'price': 0.0, 'error_message': message, 'warning_message': False}

    @api.model
    def _ncm_notify(self, title, message, notification_type='success', sticky=False):
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {'title': title, 'message': message, 'type': notification_type, 'sticky': sticky},
        }

    # Shipping provider API -----------------------------------------------------------------

    def ncm_rate_shipment(self, order):
        """The total of NCM's charges for the order's parcels (one per pickup branch)."""
        self.ensure_one()
        try:
            groups = self._ncm_rate_groups(order)
        except UserError as e:
            return self._ncm_rate_error(str(e))
        except NcmError as e:
            return self._ncm_rate_error(_("Nepal Can Move could not quote this delivery: %s", e.message))
        price = sum(charge for _branch, charge in groups)
        price = self._ncm_npr()._convert(
            price, order.currency_id, order.company_id, order.date_order or fields.Date.today(),
        )
        return {'success': True, 'price': price, 'error_message': False, 'warning_message': False}

    def _ncm_get_close_locations(self, partner_address, search=None, limit=20, **kwargs):
        """NCM branches where a customer can collect a parcel, closest first.

        `search` is what the customer typed in the location selector: a town, district or area
        name. Without one (or with a postal code), the branches of the delivery address's
        district are listed. Only 'Branch' points with coordinates are offered: NCM has not
        confirmed that 'Logistics' points hand parcels to customers.
        """
        self.ensure_one()
        Branch = self.env['ncm.branch'].sudo()
        Area = self.env['ncm.area'].sudo()
        domain = [('branch_type', '=', 'Branch'), ('latitude', '!=', 0.0)]
        home = Branch
        if partner_address and partner_address.exists():
            if partner_address.is_pickup_location and partner_address.parent_id:
                partner_address = partner_address.parent_id
            home = partner_address._ncm_get_dest_branch().sudo()

        text = normalize_name(search)
        if text and not text.isdigit():
            area_branches = Area.search([('name', 'ilike', text)], limit=300).branch_id
            branches = Branch.search(domain + [
                '|', '|', ('name', 'ilike', text), ('district', 'ilike', text),
                ('district', 'in', list(set(area_branches.mapped('district')))),
            ])
            if not branches:
                return []
            # Closest to: the branch named like the search, else the branch serving that area.
            reference = (
                branches.filtered(lambda b: text in b.name)[:1]
                or (area_branches & branches)[:1]
                or area_branches.filtered('latitude')[:1]
                or home
                or branches[:1]
            )
        elif home:
            branches = Branch.search(domain + [('district', '=', home.district)])
            reference = home
            if not branches and home.latitude:
                branches = Branch.search(domain)  # No branch in that district: offer the nearest.
        else:
            return []

        def distance(branch):
            if not reference.latitude:
                return 0.0
            lat = math.radians((branch.latitude + reference.latitude) / 2)
            dx = (branch.longitude - reference.longitude) * math.cos(lat)
            dy = branch.latitude - reference.latitude
            return dx * dx + dy * dy

        branches = branches.sorted(lambda b: (b != reference, distance(b), b.name))[:limit]
        return [branch._ncm_pickup_location_values() for branch in branches]

    def ncm_send_shipping(self, pickings):
        return [self._ncm_send_picking(picking) for picking in pickings]

    def _ncm_send_picking(self, picking):
        self.ensure_one()
        try:
            self.env.cr.execute('SELECT id FROM stock_picking WHERE id = %s FOR UPDATE NOWAIT', [picking.id])
        except Exception as e:  # LockNotAvailable: someone else is sending this transfer right now.
            raise UserError(_("%s is already being sent to NCM; try again in a moment.", picking.name)) from e

        client = self._ncm_client()
        force = self.env.context.get('ncm_force_create')
        reused = False
        log_id = 0
        if picking.ncm_order_id and picking.ncm_state not in (False, 'cancel_requested', 'cancelled'):
            # An order linked by hand ("Use this NCM order"), or one recorded by an earlier send.
            order_id = picking.ncm_order_id
            reused = True
        else:
            pending = picking._ncm_pending_attempt()
            if pending.state == 'created' and not force:
                # NCM created it, but the validation that asked for it was rolled back.
                order_id, log_id, reused = pending.ncm_order_id, pending.id, True
                picking._ncm_store_sent_values(json.loads(pending.request_payload or '{}'))
            elif pending.state == 'uncertain' and not force:
                raise UserError(_(
                    "The last attempt to create the NCM order for %(picking)s got no answer, so NCM may "
                    "have created it. Look for reference %(ref)s in the NCM vendor portal, then open the "
                    "transfer and either enter that order's number and click 'Use this NCM order', or "
                    "click 'Create NCM order anyway'.",
                    picking=picking.name, ref=pending.vref or picking.name,
                ))
            else:
                values = picking._ncm_prepare_order_values()
                try:
                    order_id = client.create_order(values)
                except NcmError as e:
                    self._ncm_record_attempt(
                        picking, values, 'uncertain' if e.uncertain else 'error', message=e.message,
                    )
                    if e.uncertain:
                        raise UserError(_(
                            "NCM did not confirm the order for %(picking)s (%(error)s), so it may or may "
                            "not exist. Look for reference %(ref)s in the NCM vendor portal before trying "
                            "again: the transfer now shows what to do.",
                            picking=picking.name, error=e.message, ref=values['vref_id'],
                        )) from e
                    raise UserError(_(
                        "Nepal Can Move refused the order for %(picking)s: %(error)s",
                        picking=picking.name, error=e.message,
                    )) from e
                log_id = self._ncm_record_attempt(picking, values, 'created', order_id=order_id)
                picking._ncm_store_sent_values(values)

        # NCM holds the order from here on: nothing below may raise, or a retry could duplicate it.
        charge = picking._ncm_after_order_created(client, order_id, log_id)
        if reused:
            picking.message_post(
                body=_("Using NCM order %s, which already exists at NCM.", order_id),
                subtype_xmlid='mail.mt_note',
            )
        company = picking.company_id
        exact_price = self._ncm_npr()._convert(charge, company.currency_id, company, fields.Date.today())
        return {'exact_price': exact_price, 'tracking_number': str(order_id)}

    def _ncm_record_attempt(self, picking, values, state, order_id=0, message=False):
        """Log an order-creation attempt through a separate cursor, so it outlives a rollback."""
        log_values = {
            'carrier_id': self.id,
            'environment': self._ncm_environment(),
            'picking_res_id': picking.id,
            'picking_name': picking.name,
            'vref': values.get('vref_id'),
            'state': state,
            'ncm_order_id': order_id or 0,
            'request_payload': json.dumps(values, ensure_ascii=False),
            'message': message,
        }
        try:
            with self.env.registry.cursor() as cr:
                env = api.Environment(cr, SUPERUSER_ID, {})
                return env['ncm.api.log'].create(log_values).id
        except Exception:
            _logger.exception("Could not record the NCM order attempt for %s", picking.name)
            return 0

    def ncm_get_tracking_link(self, picking):
        if self.tracking_url and picking.carrier_tracking_ref:
            return self.tracking_url.replace('<shipmenttrackingnumber>', picking.carrier_tracking_ref)
        return False

    def ncm_cancel_shipment(self, pickings):
        """NCM's API cannot cancel an order: ask NCM through a comment and leave a to-do."""
        client = self._ncm_client()
        for picking in pickings.filtered('ncm_order_id'):
            try:
                client.post_comment(picking.ncm_order_id, "Please cancel this order (cancelled by the vendor).")
                sent = _("A cancellation request was posted as a comment on the NCM order.")
            except NcmError as e:
                sent = _("Posting the cancellation request on NCM failed: %s", e.message)
            picking.ncm_state = 'cancel_requested'
            picking.message_post(
                body=Markup("%s<br/>%s") % (_("NCM order %s: cancellation requested.", picking.ncm_order_id), sent),
                subtype_xmlid='mail.mt_note',
            )
            picking.activity_schedule(
                'mail.mail_activity_data_todo',
                summary=_("Cancel NCM order %s", picking.ncm_order_id),
                note=_(
                    "NCM's API cannot cancel orders. Cancel order %s in the NCM vendor portal or by "
                    "phone, then mark this activity done.", picking.ncm_order_id,
                ),
                user_id=picking.user_id.id or self.env.uid,
            )

    # Buttons -------------------------------------------------------------------------------

    def action_ncm_sync_branches(self):
        try:
            result = self.env['ncm.branch'].sudo()._ncm_sync()
        except NcmError as e:
            raise UserError(_("Could not fetch NCM's branches: %s", e.message)) from e
        return self._ncm_notify(_("NCM branches updated"), _(
            "%(created)s added, %(updated)s changed, %(archived)s archived.", **result,
        ))

    def action_ncm_check_account(self):
        self.ensure_one()
        try:
            branches = self._ncm_client().get_assigned_branches()
        except NcmError as e:
            raise UserError(_("NCM did not accept the token: %s", e.message)) from e
        if not branches:
            return self._ncm_notify(
                _("Token works"), _("NCM has not assigned any pickup branch to this account yet."), 'warning', True,
            )
        message = _("Pickup branches assigned to this account: %s.", ', '.join(branches))
        used = (
            self.ncm_from_branch_id
            | self.env['product.template'].search([('ncm_pickup_branch_id', '!=', False)]).ncm_pickup_branch_id
            | self.env['stock.warehouse'].search([('ncm_pickup_branch_id', '!=', False)]).ncm_pickup_branch_id
        )
        unassigned = used.filtered(lambda branch: branch.name not in branches)
        if unassigned:
            message += ' ' + _(
                "These pickup branches set on this method, products or warehouses are not among them: %s.",
                ', '.join(unassigned.mapped('name')),
            )
            return self._ncm_notify(_("Token works"), message, 'warning', True)
        return self._ncm_notify(_("Token works"), message, sticky=True)

    def action_ncm_register_webhook(self):
        self.ensure_one()
        url = self.sudo().ncm_webhook_url
        try:
            self._ncm_client().set_status_webhook(url)
        except NcmError as e:
            raise UserError(_("NCM did not accept the webhook: %s", e.message)) from e
        return self._ncm_notify(_("Webhook registered"), _(
            "NCM will send status changes to %s. NCM's API only sets the delivery webhook: paste the same "
            "address in the 'Order Comment Webhook URL' field of the vendor portal yourself.", url,
        ), sticky=True)

    def action_ncm_test_webhook(self):
        self.ensure_one()
        try:
            result = self._ncm_client().test_webhook(self.sudo().ncm_webhook_url)
        except NcmError as e:
            raise UserError(_("NCM could not run the test: %s", e.message)) from e
        if result.get('success') and result.get('status_code') == 200:
            return self._ncm_notify(_("Webhook reachable"), _("NCM reached this database and got HTTP 200."))
        detail = result.get('error') or f"HTTP {result.get('status_code')} {result.get('response') or ''}"
        return self._ncm_notify(_("Webhook test failed"), detail, 'danger', True)

    # Scheduled jobs ------------------------------------------------------------------------

    @api.model
    def _ncm_accounts(self):
        """NCM carriers grouped by account: {(environment, token): carriers}."""
        accounts = defaultdict(lambda: self.browse())
        for carrier in self.sudo().search([('delivery_type', '=', 'ncm')]):
            if carrier.ncm_api_token:
                accounts[(carrier._ncm_environment(), carrier.ncm_api_token)] |= carrier
        return accounts

    @api.model
    def _ncm_commit_progress(self, processed):
        if self.env.context.get('ir_cron_progress_id'):
            self.env['ir.cron']._commit_progress(processed)

    @api.model
    def _ncm_cron_sync_branches(self):
        if not self.sudo().search_count([('delivery_type', '=', 'ncm')]):
            return
        try:
            self.env['ncm.branch'].sudo()._ncm_sync()
        except NcmError as e:
            _logger.warning("NCM branch sync failed: %s", e.message)

    @api.model
    def _ncm_cron_sync_status(self):
        Picking = self.env['stock.picking'].sudo()
        since = fields.Datetime.now() - timedelta(days=const.STATUS_SYNC_MAX_AGE_DAYS)
        for carriers in self._ncm_accounts().values():
            pickings = Picking.search([
                ('carrier_id', 'in', carriers.ids),
                ('ncm_order_id', '!=', 0),
                ('ncm_state', 'not in', const.FINAL_STATES),
                '|', ('date_done', '>=', since), ('date_done', '=', False),
            ])
            if pickings:
                pickings._ncm_sync_statuses(carriers[0]._ncm_client())

    @api.model
    def _ncm_cron_sync_comments(self):
        Picking = self.env['stock.picking'].sudo()
        for carriers in self._ncm_accounts().values():
            try:
                rows = carriers[0]._ncm_client().get_bulk_comments()
            except NcmError as e:
                _logger.warning("NCM comment sync failed: %s", e.message)
                continue
            by_order = defaultdict(list)
            for row in rows:
                try:
                    by_order[int(row.get('orderid'))].append(row)
                except (TypeError, ValueError):
                    continue
            pickings = Picking.search([('carrier_id', 'in', carriers.ids), ('ncm_order_id', 'in', list(by_order))])
            for picking in pickings:
                picking._ncm_store_comment_rows(by_order[picking.ncm_order_id])

    # Webhooks ------------------------------------------------------------------------------

    def _ncm_receive_webhook(self, raw_body, payload):
        """Queue an NCM webhook call. Processing re-reads the order from NCM's API, so a forged
        payload can at worst trigger a refresh."""
        self.ensure_one()
        order_id = extract_order_id(payload)
        is_test = str(payload.get('test')).lower() == 'true' if isinstance(payload, dict) else False
        if is_test:
            state, note = 'ignored', "Test call"
        elif not order_id:
            state, note = 'ignored', "No order number in the payload"
        else:
            state, note = 'pending', False
        event = self.env['ncm.webhook.event'].sudo().create({
            'carrier_id': self.id,
            'ncm_order_id': order_id,
            'payload': (raw_body or '')[:10000],
            'state': state,
            'note': note,
        })
        if state == 'pending':
            self.env.ref('delivery_ncm.ir_cron_ncm_process_webhooks').sudo()._trigger()
        return event

    @api.model
    def _ncm_cron_process_webhooks(self):
        Event = self.env['ncm.webhook.event'].sudo()
        Picking = self.env['stock.picking'].sudo()
        give_up_before = fields.Datetime.now() - timedelta(hours=const.WEBHOOK_EVENT_GIVE_UP_HOURS)
        refreshed = set()
        for event in Event.search([('state', '=', 'pending')], order='id', limit=500):
            picking = Picking.search([
                ('ncm_order_id', '=', event.ncm_order_id),
                ('carrier_id.delivery_type', '=', 'ncm'),
            ], order='id desc', limit=1)
            if not picking:
                # The webhook can beat the commit of the validation that created the order.
                if event.create_date < give_up_before:
                    event.write({'state': 'ignored', 'note': "No transfer has this NCM order"})
                else:
                    event.attempts += 1
                continue
            if picking.id not in refreshed:
                try:
                    picking._ncm_refresh(picking.carrier_id._ncm_client())
                except (NcmError, UserError) as e:
                    event.write({
                        'attempts': event.attempts + 1,
                        'note': str(e)[:250],
                        'state': 'ignored' if event.attempts >= 4 else 'pending',
                    })
                    continue
                refreshed.add(picking.id)
            event.state = 'done'
            self._ncm_commit_progress(1)
