# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import UserError


class EmiVendor(models.Model):
    """A marketplace seller. Vendor staff get portal access scoped to their
    own products, orders and settlement statements via ir.rule.

    Onboarding is manual approval by default (draft -> pending -> approved).
    A later 'auto-approve' path can be added by calling action_approve()
    from a server action / automation rule instead of the button, without
    changing this model.
    """
    _name = 'emi.vendor'
    _description = 'EMI Marketplace Vendor'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'name'

    partner_id = fields.Many2one(
        'res.partner', string='Vendor Contact', required=True, ondelete='restrict',
        tracking=True,
    )
    name = fields.Char(related='partner_id.name', store=True, readonly=True)
    active = fields.Boolean(default=True)

    state = fields.Selection(
        [
            ('draft', 'Draft'),
            ('pending', 'Pending Review'),
            ('approved', 'Approved'),
            ('suspended', 'Suspended'),
            ('rejected', 'Rejected'),
        ],
        default='draft', required=True, tracking=True,
    )

    commission_type = fields.Selection(
        [('percent', 'Percentage of Sale'), ('fixed', 'Fixed Amount per Sale')],
        default='percent', required=True,
    )
    commission_value = fields.Float(required=True, default=10.0)

    settlement_frequency = fields.Selection(
        [('weekly', 'Weekly'), ('biweekly', 'Bi-weekly'), ('monthly', 'Monthly')],
        default='monthly', required=True,
        help="How often emi_accounting batches this vendor's sales into a settlement run.",
    )
    settlement_bank_account_id = fields.Many2one('res.partner.bank', string='Payout Bank Account')

    product_ids = fields.One2many('product.template', 'vendor_id', string='Products')
    product_count = fields.Integer(compute='_compute_product_count')

    onboarding_document_ids = fields.Many2many(
        'ir.attachment', string='Onboarding Documents',
        help="KYB documents: business registration, PAN/VAT certificate, bank details, etc.",
    )

    user_ids = fields.Many2many(
        'res.users', string='Portal Users',
        domain=[('share', '=', True)],
        help="Portal users allowed to manage this vendor's products and view settlements.",
    )

    @api.depends('product_ids')
    def _compute_product_count(self):
        for rec in self:
            rec.product_count = len(rec.product_ids)

    def action_submit(self):
        for rec in self:
            if rec.state != 'draft':
                raise UserError("Only draft vendors can be submitted for review.")
            rec.state = 'pending'

    def action_approve(self):
        for rec in self:
            if rec.state not in ('pending', 'suspended'):
                raise UserError("Only vendors pending review or suspended can be approved.")
            rec.state = 'approved'

    def action_reject(self):
        for rec in self:
            if rec.state != 'pending':
                raise UserError("Only vendors pending review can be rejected.")
            rec.state = 'rejected'

    def action_suspend(self):
        for rec in self:
            if rec.state != 'approved':
                raise UserError("Only approved vendors can be suspended.")
            rec.state = 'suspended'

    def action_view_products(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Products',
            'res_model': 'product.template',
            'view_mode': 'list,form',
            'domain': [('vendor_id', '=', self.id)],
            'context': {'default_vendor_id': self.id},
        }
