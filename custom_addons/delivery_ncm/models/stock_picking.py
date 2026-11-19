# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging
import re
from datetime import datetime, timezone

from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import float_round

from odoo.addons.delivery_ncm import const
from odoo.addons.delivery_ncm.models.ncm_request import NcmError

_logger = logging.getLogger(__name__)

NOT_SENT_STATES = (False, 'cancel_requested', 'cancelled')


def normalize_phone(raw):
    """Digits only, without Nepal's +977 prefix; landlines keep their leading 0 (e.g. 015970736)."""
    digits = re.sub(r'\D', '', raw or '')
    if digits.startswith('00'):
        digits = digits[2:]
    if digits.startswith('977') and len(digits) > 10:
        digits = digits[3:]
        if not digits.startswith(('9', '0')):
            digits = '0' + digits
    return digits


def format_amount(value):
    return ('%.2f' % (value or 0.0)).rstrip('0').rstrip('.')


def parse_ncm_datetime(value):
    """'2019-10-18T13:24:30.960365+05:45' -> naive UTC datetime (Odoo's storage format)."""
    if not value:
        return False
    try:
        parsed = datetime.fromisoformat(str(value).strip())
    except ValueError:
        return False
    if parsed.tzinfo:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed.replace(microsecond=0)


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    ncm_order_id = fields.Integer(
        string="NCM Order", copy=False, index='btree_not_null',
        help="Order number in the NCM portal.",
    )
    ncm_dest_branch_id = fields.Many2one(
        'ncm.branch', string="NCM Destination Branch", copy=False,
        compute='_compute_ncm_dest_branch_id', store=True, readonly=False,
        help="The NCM branch that delivers to the customer, or where the customer collects the parcel. "
             "Found from the address's NCM delivery area; change it here if it is wrong.",
    )
    ncm_cod_amount = fields.Float(
        string="Cash to Collect", digits='Product Price', copy=False,
        compute='_compute_ncm_cod_amount', store=True, readonly=False,
        help="Cash NCM collects from the customer, delivery charge included (NPR). Computed from what "
             "the customer still owes on the sales order; set 0 when already paid.",
    )
    ncm_instruction = fields.Char(string="Delivery Instruction", copy=False, help="Shown to NCM's rider.")
    ncm_state = fields.Selection(const.NCM_STATES, string="NCM Stage", copy=False, readonly=True, index=True)
    ncm_status = fields.Char(string="NCM Status", copy=False, readonly=True, help="Last status, as NCM words it.")
    ncm_status_date = fields.Datetime(string="NCM Status Since", copy=False, readonly=True)
    ncm_delivery_charge = fields.Float(string="NCM Delivery Charge", copy=False, readonly=True)
    ncm_payment_status = fields.Char(string="NCM Payment Status", copy=False, readonly=True)
    ncm_track_id = fields.Char(string="NCM Track ID", copy=False, readonly=True, help="NCM's tracking code (trackid).")
    ncm_vref = fields.Char(string="NCM Reference", copy=False, readonly=True)
    ncm_package_description = fields.Char(string="NCM Package", copy=False, readonly=True)
    ncm_weight = fields.Float(string="NCM Weight (kg)", copy=False, readonly=True)
    ncm_status_ids = fields.One2many('ncm.order.status', 'picking_id', string="NCM Status History")
    ncm_comment_ids = fields.One2many('ncm.order.comment', 'picking_id', string="NCM Comments")
    ncm_log_checkpoint = fields.Integer(copy=False, help="Technical: last ncm.api.log row already handled.")
    ncm_needs_check = fields.Boolean(compute='_compute_ncm_needs_check')

    @api.depends('carrier_id.delivery_type', 'partner_id.ncm_area_id', 'partner_id.city', 'sale_id')
    def _compute_ncm_dest_branch_id(self):
        for picking in self:
            if picking.carrier_id.delivery_type != 'ncm' or not picking.partner_id:
                picking.ncm_dest_branch_id = False
            elif picking.ncm_state not in NOT_SENT_STATES:
                picking.ncm_dest_branch_id = picking.ncm_dest_branch_id  # Already at NCM: keep.
            elif picking.sale_id:
                picking.ncm_dest_branch_id = picking.sale_id._ncm_get_dest_branch(
                    picking.partner_id, carrier=picking.carrier_id,
                )
            else:
                picking.ncm_dest_branch_id = picking._ncm_customer()._ncm_get_dest_branch()

    @api.depends(
        'carrier_id.delivery_type', 'sale_id.amount_total',
        'sale_id.transaction_ids.state', 'sale_id.transaction_ids.amount',
    )
    def _compute_ncm_cod_amount(self):
        npr = self.env.ref('base.NPR')
        for picking in self:
            sale = picking.sale_id
            if picking.ncm_state not in NOT_SENT_STATES:
                picking.ncm_cod_amount = picking.ncm_cod_amount  # Already at NCM: keep.
            elif picking.carrier_id.delivery_type != 'ncm' or not sale:
                picking.ncm_cod_amount = 0.0
            else:
                # Only the first NCM shipment of an order collects the cash.
                others = sale.picking_ids.filtered(
                    lambda p: p != picking and p.ncm_order_id and p.ncm_state not in NOT_SENT_STATES
                )
                due = sale.amount_total - sale.amount_paid
                if sale.currency_id != npr:
                    due = sale.currency_id._convert(due, npr, picking.company_id, fields.Date.today())
                due -= sum(others.mapped('ncm_cod_amount'))
                picking.ncm_cod_amount = float_round(max(due, 0.0), precision_digits=2)

    def _compute_ncm_needs_check(self):
        for picking in self:
            picking.ncm_needs_check = (
                picking.delivery_type == 'ncm'
                and not picking.carrier_tracking_ref
                and picking._ncm_pending_attempt().state == 'uncertain'
            )

    # Sending -------------------------------------------------------------------------------

    def _ncm_pending_attempt(self):
        """The latest order-creation attempt not yet handled by this transfer."""
        self.ensure_one()
        Log = self.env['ncm.api.log'].sudo()
        if not isinstance(self.id, int):
            return Log
        return Log.search([
            ('picking_res_id', '=', self.id),
            ('id', '>', self.ncm_log_checkpoint),
            ('state', 'in', ('created', 'uncertain')),
        ], order='id desc', limit=1)

    def _ncm_customer(self):
        """The person receiving the parcel. For collect-at-branch orders Odoo replaces the
        delivery address with a contact named after the branch; the customer is its parent."""
        self.ensure_one()
        partner = self.partner_id
        if partner.is_pickup_location and partner.parent_id:
            return partner.parent_id
        return partner

    def _ncm_phones(self):
        self.ensure_one()
        partner = self._ncm_customer()
        phones = []
        for raw in (partner.phone, partner.commercial_partner_id.phone):
            phone = normalize_phone(raw)
            if phone and phone not in phones:
                phones.append(phone)
        return (phones + ['', ''])[:2]

    def _ncm_address(self):
        self.ensure_one()
        partner = self._ncm_customer()
        parts = []
        for text in (partner.street, partner.street2, partner.ncm_area_id.name, partner.city):
            text = (text or '').strip()
            if text and text.lower() not in ', '.join(parts).lower():
                parts.append(text)
        return ', '.join(parts)

    def _ncm_package_description(self):
        self.ensure_one()
        parts = []
        for move in self.move_ids.filtered(lambda m: m.state != 'cancel' and m.product_id):
            quantity = move.quantity or move.product_uom_qty
            name = move.product_id.with_context(display_default_code=False).display_name
            parts.append(f"{name} x{format_amount(quantity)}")
        return ', '.join(parts)[:150]

    def _ncm_reference(self):
        self.ensure_one()
        sale = self.sale_id
        if not sale:
            return self.name
        others = sale.picking_ids.filtered(lambda p: p != self and p.ncm_order_id)
        return f"{sale.name}-{self.name.rsplit('/', 1)[-1]}" if others else sale.name

    def _ncm_weight_kg(self):
        self.ensure_one()
        weight = self.carrier_id._ncm_to_kg(self.shipping_weight or self.weight)
        return max(1.0, float_round(weight, precision_digits=2))

    def _ncm_prepare_order_values(self):
        self.ensure_one()
        carrier = self.carrier_id
        partner = self._ncm_customer()
        phone, phone2 = self._ncm_phones()
        address = self._ncm_address()
        missing = []
        if not carrier.ncm_from_branch_id:
            missing.append(_("the pickup branch on the delivery method"))
        if not self.ncm_dest_branch_id:
            missing.append(_("the NCM destination branch (set the customer's NCM delivery area)"))
        if not (partner.name or partner.parent_id.name):
            missing.append(_("the customer's name"))
        if not phone:
            missing.append(_("the customer's phone number"))
        if not address:
            missing.append(_("the delivery address"))
        if missing:
            raise UserError(_(
                "Before sending %(picking)s to Nepal Can Move, add %(missing)s.",
                picking=self.name, missing=', '.join(missing),
            ))
        return {
            'name': (partner.name or partner.parent_id.name).strip(),
            'phone': phone,
            'phone2': phone2,
            'cod_charge': format_amount(self.ncm_cod_amount),
            'address': address,
            'fbranch': carrier.ncm_from_branch_id.name,
            'branch': self.ncm_dest_branch_id.name,
            'package': self._ncm_package_description(),
            'vref_id': self._ncm_reference(),
            'instruction': (self.ncm_instruction or '').strip(),
            'delivery_type': carrier.ncm_delivery_type or 'Door2Door',
            'weight': format_amount(self._ncm_weight_kg()),
        }

    def _ncm_store_sent_values(self, values):
        self.ensure_one()
        try:
            weight = float(values.get('weight') or 0.0)
        except ValueError:
            weight = 0.0
        self.write({
            'ncm_vref': values.get('vref_id'),
            'ncm_package_description': values.get('package'),
            'ncm_weight': weight,
        })

    def _ncm_after_order_created(self, client, order_id, log_id):
        """Record an order NCM holds. Never raises; returns NCM's delivery charge (NPR)."""
        self.ensure_one()
        last_log = self.env['ncm.api.log'].sudo().search([('picking_res_id', '=', self.id)], order='id desc', limit=1)
        self.write({
            'ncm_order_id': order_id,
            'ncm_state': 'created',
            'ncm_status': False,
            'ncm_status_date': fields.Datetime.now(),
            'ncm_delivery_charge': 0.0,
            'ncm_payment_status': False,
            'ncm_track_id': False,
            'ncm_log_checkpoint': max(log_id, last_log.id, self.ncm_log_checkpoint),
        })
        try:
            self._ncm_apply_detail(client.get_order(order_id))
        except NcmError as e:
            _logger.warning("NCM order %s created, but reading it back failed: %s", order_id, e.message)
        if not self.ncm_delivery_charge and self.ncm_dest_branch_id:
            try:
                self.ncm_delivery_charge = self.carrier_id._ncm_get_rate(self.ncm_dest_branch_id)
            except (NcmError, UserError):
                pass
        try:
            self._ncm_attach_label()
        except Exception as e:
            if isinstance(e, UserError):  # e.g. wkhtmltopdf missing
                _logger.warning("Could not render the NCM label of %s: %s", self.name, e)
            else:
                _logger.exception("Could not render the NCM label of %s", self.name)
            self.message_post(
                body=_("NCM order %s was created, but its label could not be generated; print it from the transfer.", order_id),
                subtype_xmlid='mail.mt_note',
            )
        return self.ncm_delivery_charge

    def _ncm_attach_label(self):
        self.ensure_one()
        pdf, _content_type = self.env['ir.actions.report']._render_qweb_pdf(
            'delivery_ncm.action_report_ncm_label', self.ids,
        )
        name = f"{self.carrier_id._get_delivery_label_prefix()}-{self.ncm_order_id}.pdf"
        self.message_post(
            body=_("Nepal Can Move label for order %s", self.ncm_order_id),
            attachments=[(name, pdf)],
            subtype_xmlid='mail.mt_note',
        )

    # Status and comments ---------------------------------------------------------------------

    def _ncm_set_current_status(self, status, date=None):
        self.ensure_one()
        state = const.status_to_state(status)
        if self.ncm_state == 'cancel_requested' and state not in const.FINAL_STATES:
            state = 'cancel_requested'  # Still waiting for NCM to act on our request.
        changed = state != self.ncm_state
        self.write({'ncm_status': status, 'ncm_state': state, 'ncm_status_date': date or fields.Datetime.now()})
        if changed and state in ('delivered', 'returning', 'returned', 'cancelled', 'exception'):
            self.message_post(
                body=_("NCM order %(order)s: %(status)s", order=self.ncm_order_id, status=status),
                subtype_xmlid='mail.mt_note',
            )
        if changed and state in ('out_for_delivery', 'delivered') and self.carrier_id.ncm_notify_customer:
            self._ncm_notify_customer(state)

    def _ncm_notify_customer(self, state):
        """Email the customer that the parcel is on its way, or delivered."""
        self.ensure_one()
        template = self.env.ref(
            'delivery_ncm.mail_template_ncm_out_for_delivery' if state == 'out_for_delivery'
            else 'delivery_ncm.mail_template_ncm_delivered',
            raise_if_not_found=False,
        )
        customer = self.sale_id.partner_id or self._ncm_customer()
        if not template or not customer.email:
            return
        try:
            with self.env.cr.savepoint():
                self.message_post_with_source(
                    template,
                    email_layout_xmlid='mail.mail_notification_light',
                    subtype_xmlid='mail.mt_comment',
                )
        except Exception:  # A mail problem must never break status syncing.
            _logger.exception("Could not email %s about NCM order %s", customer.email, self.ncm_order_id)

    def _ncm_apply_status_history(self, rows):
        """Store NCM's status history (newest first, as NCM sends it) and the current status."""
        self.ensure_one()
        known = {
            (line.status, line.date)
            for line in self.ncm_status_ids if line.ncm_order_id == self.ncm_order_id
        }
        parsed = []
        for row in rows:
            status = (row.get('status') or '').strip()
            if status:
                parsed.append((parse_ncm_datetime(row.get('added_time')) or fields.Datetime.now(), status))
        parsed.sort()
        new_lines = [
            {
                'picking_id': self.id,
                'ncm_order_id': self.ncm_order_id,
                'status': status,
                'ncm_state': const.status_to_state(status),
                'date': date,
            }
            for date, status in parsed if (status, date) not in known
        ]
        if new_lines:
            self.env['ncm.order.status'].sudo().create(new_lines)
        if parsed and (parsed[-1][1] != self.ncm_status or parsed[-1][0] != self.ncm_status_date):
            self._ncm_set_current_status(parsed[-1][1], parsed[-1][0])

    def _ncm_apply_detail(self, detail):
        self.ensure_one()
        if not isinstance(detail, dict):
            return
        values = {}
        try:
            if detail.get('delivery_charge') not in (None, ''):
                values['ncm_delivery_charge'] = float(detail['delivery_charge'])
        except (TypeError, ValueError):
            pass
        if detail.get('payment_status'):
            values['ncm_payment_status'] = str(detail['payment_status'])
        if detail.get('trackid'):  # Undocumented, but returned by the order endpoint.
            values['ncm_track_id'] = str(detail['trackid'])
        if values:
            self.write(values)
        if detail.get('last_delivery_status') and not self.ncm_status:
            self._ncm_set_current_status(str(detail['last_delivery_status']))

    def _ncm_store_comment_rows(self, rows):
        """Store new NCM comments; those from NCM staff also go to the chatter as notes."""
        self.ensure_one()
        Comment = self.env['ncm.order.comment'].sudo()
        root = self.env.ref('base.partner_root')
        for row in sorted(rows, key=lambda r: str(r.get('added_time') or '')):
            body = (row.get('comments') or '').strip()
            if not body:
                continue
            added_time = row.get('added_time') or ''
            key = Comment._make_key(self.ncm_order_id, added_time, body)
            if Comment.search_count([('key', '=', key)]):
                continue
            added_by = (row.get('addedBy') or row.get('added_by') or '').strip()
            Comment.create({
                'picking_id': self.id,
                'ncm_order_id': self.ncm_order_id,
                'body': body,
                'added_by': added_by,
                'date': parse_ncm_datetime(added_time) or fields.Datetime.now(),
                'key': key,
            })
            if added_by.lower() != 'vendor':
                self.message_post(
                    body=Markup("<b>%s</b><br/>%s") % (_("Comment from %s on NCM:", added_by or "NCM"), body),
                    subtype_xmlid='mail.mt_note',
                    author_id=root.id,
                )

    def _ncm_refresh(self, client):
        """Re-read status history, charges and comments of each transfer's NCM order."""
        for picking in self.filtered('ncm_order_id'):
            order_id = picking.ncm_order_id
            picking._ncm_apply_status_history(client.get_order_statuses(order_id))
            picking._ncm_apply_detail(client.get_order(order_id))
            picking._ncm_store_comment_rows(client.get_order_comments(order_id))

    def _ncm_sync_statuses(self, client):
        """Check many orders in bulk calls, then fully refresh only those whose status changed."""
        by_order = {picking.ncm_order_id: picking for picking in self if picking.ncm_order_id}
        order_ids = list(by_order)
        for start in range(0, len(order_ids), const.STATUS_BATCH_SIZE):
            chunk = order_ids[start:start + const.STATUS_BATCH_SIZE]
            try:
                result, errors = client.get_statuses(chunk)
            except NcmError as e:
                _logger.warning("NCM bulk status request failed: %s", e.message)
                return
            if errors:
                _logger.info("NCM does not know these orders: %s", errors)
            for key, status in result.items():
                try:
                    picking = by_order.get(int(key))
                except (TypeError, ValueError):
                    continue
                if not picking or not status or status == picking.ncm_status:
                    continue
                try:
                    picking._ncm_refresh(client)
                except NcmError as e:
                    _logger.warning("Refreshing NCM order %s failed: %s", key, e.message)
                    picking._ncm_set_current_status(status)
            self.env['delivery.carrier']._ncm_commit_progress(len(chunk))

    # Buttons -------------------------------------------------------------------------------

    def action_ncm_refresh(self):
        for picking in self.filtered(lambda p: p.delivery_type == 'ncm' and p.ncm_order_id):
            try:
                picking._ncm_refresh(picking.carrier_id._ncm_client())
            except NcmError as e:
                raise UserError(_(
                    "Could not refresh NCM order %(order)s: %(error)s", order=picking.ncm_order_id, error=e.message,
                )) from e
        return True

    def action_ncm_message(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Message NCM"),
            'res_model': 'ncm.comment.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_picking_id': self.id},
        }

    def action_ncm_force_create(self):
        """Create a new NCM order although an earlier attempt's outcome is unknown."""
        self.ensure_one()
        picking = self.with_context(ncm_force_create=True)
        if self.state == 'done':
            return picking.send_to_shipper()
        return picking.button_validate()

    def action_ncm_link_order(self):
        """Use an order that already exists at NCM (its number typed into the NCM Order field)."""
        self.ensure_one()
        if not self.ncm_order_id:
            raise UserError(_("Type the NCM order number first."))
        try:
            detail = self.carrier_id._ncm_client().get_order(self.ncm_order_id)
        except NcmError as e:
            raise UserError(_(
                "NCM does not know order %(order)s for this account: %(error)s",
                order=self.ncm_order_id, error=e.message,
            )) from e
        last_log = self.env['ncm.api.log'].sudo().search([('picking_res_id', '=', self.id)], order='id desc', limit=1)
        self.write({'ncm_state': 'created', 'ncm_log_checkpoint': max(last_log.id, self.ncm_log_checkpoint)})
        self._ncm_apply_detail(detail)
        if self.state == 'done' and not self.carrier_tracking_ref:
            return self.send_to_shipper()
        self.message_post(
            body=_("Linked to existing NCM order %s.", self.ncm_order_id), subtype_xmlid='mail.mt_note',
        )
        return True
