# Part of Odoo. See LICENSE file for full copyright and licensing details.

import hashlib

from odoo import fields, models

from odoo.addons.delivery_ncm import const


class NcmOrderStatus(models.Model):
    _name = 'ncm.order.status'
    _description = "NCM Order Status"
    _order = 'date desc, id desc'

    picking_id = fields.Many2one('stock.picking', required=True, index=True, ondelete='cascade')
    ncm_order_id = fields.Integer(string="NCM Order", index=True)
    status = fields.Char(required=True, help="Status text exactly as NCM sent it.")
    ncm_state = fields.Selection(const.NCM_STATES, string="Stage")
    date = fields.Datetime(required=True, default=fields.Datetime.now)


class NcmOrderComment(models.Model):
    _name = 'ncm.order.comment'
    _description = "NCM Order Comment"
    _order = 'date desc, id desc'

    picking_id = fields.Many2one('stock.picking', required=True, index=True, ondelete='cascade')
    ncm_order_id = fields.Integer(string="NCM Order", index=True)
    body = fields.Text(required=True)
    added_by = fields.Char(help="'NCM Staff' or 'Vendor', as NCM reports it.")
    date = fields.Datetime(required=True, default=fields.Datetime.now)
    key = fields.Char(required=True, index=True, help="Fingerprint used to skip comments already stored.")

    _key_uniq = models.Constraint('UNIQUE(key)', "This NCM comment is already stored.")

    @staticmethod
    def _make_key(ncm_order_id, added_time, body):
        raw = f'{ncm_order_id}|{added_time}|{body}'
        return hashlib.sha1(raw.encode()).hexdigest()


class NcmApiLog(models.Model):
    """Every order-creation attempt, written through a separate cursor.

    It survives a rollback of the delivery validation, so a retry can reuse an order NCM
    already created instead of creating a duplicate (NCM has no idempotency key and no
    lookup by our reference).
    """
    _name = 'ncm.api.log'
    _description = "NCM Order Creation Attempt"
    _order = 'id desc'

    carrier_id = fields.Many2one('delivery.carrier', ondelete='set null')
    environment = fields.Selection([('demo', "Demo"), ('production', "Production")])
    picking_res_id = fields.Integer(string="Transfer ID", index=True)
    picking_name = fields.Char(string="Transfer")
    vref = fields.Char(string="Our Reference")
    state = fields.Selection([
        ('created', "Created"),
        ('error', "Refused"),
        ('uncertain', "Unknown outcome"),
    ], required=True)
    ncm_order_id = fields.Integer(string="NCM Order")
    request_payload = fields.Text()
    message = fields.Text()


class NcmWebhookEvent(models.Model):
    _name = 'ncm.webhook.event'
    _description = "NCM Webhook Event"
    _order = 'id desc'

    carrier_id = fields.Many2one('delivery.carrier', ondelete='cascade')
    ncm_order_id = fields.Integer(string="NCM Order", index=True)
    payload = fields.Text()
    state = fields.Selection([
        ('pending', "Pending"),
        ('done', "Processed"),
        ('ignored', "Ignored"),
    ], default='pending', required=True, index=True)
    attempts = fields.Integer()
    note = fields.Char()
