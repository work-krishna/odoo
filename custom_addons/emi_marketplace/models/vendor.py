# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError


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
        default='draft', required=True, tracking=True, copy=False,
    )

    commission_type = fields.Selection(
        [('percent', 'Percentage of Sale'), ('fixed', 'Fixed Amount per Sale')],
        default='percent', required=True, tracking=True,
    )
    commission_value = fields.Float(required=True, default=10.0, tracking=True)
    currency_id = fields.Many2one(
        'res.currency', required=True,
        default=lambda self: self.env['res.company']._emi_get_marketplace_company().currency_id,
        help="Currency of a fixed commission amount.",
    )

    settlement_frequency = fields.Selection(
        [('weekly', 'Weekly'), ('biweekly', 'Bi-weekly'), ('monthly', 'Monthly')],
        default='monthly', required=True, tracking=True,
        help="How often emi_accounting batches this vendor's sales into a settlement run.",
    )
    settlement_bank_account_id = fields.Many2one(
        'res.partner.bank', string='Payout Bank Account', ondelete='restrict', tracking=True,
        domain="[('partner_id', 'child_of', partner_id)]",
    )

    product_ids = fields.One2many('product.template', 'vendor_id', string='Products')
    product_count = fields.Integer(compute='_compute_product_count')

    onboarding_document_ids = fields.Many2many(
        'ir.attachment', string='Onboarding Documents',
        help="KYB documents: business registration, PAN/VAT certificate, bank details, etc.",
    )

    user_ids = fields.Many2many(
        'res.users', string='Portal Users', copy=False,
        domain=[('share', '=', True)],
        help="Portal users allowed to manage this vendor's products and view settlements. "
             "They are added to the Vendor Portal User group automatically.",
    )

    @api.depends('product_ids')
    def _compute_product_count(self):
        for rec in self:
            rec.product_count = len(rec.product_ids)

    @api.constrains('commission_type', 'commission_value')
    def _check_commission(self):
        for rec in self:
            if rec.commission_value < 0:
                raise ValidationError("The commission cannot be negative.")
            if rec.commission_type == 'percent' and rec.commission_value > 100:
                raise ValidationError("A percentage commission cannot exceed 100%.")

    @api.constrains('settlement_bank_account_id', 'partner_id')
    def _check_settlement_bank_account(self):
        for rec in self:
            bank = rec.settlement_bank_account_id
            if bank and bank.partner_id.commercial_partner_id != rec.partner_id.commercial_partner_id:
                raise ValidationError("The payout bank account must belong to the vendor.")

    # ------------------------------------------------------------------
    # Portal user <-> group sync
    # ------------------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        vendors = super().create(vals_list)
        vendors._sync_vendor_portal_group(self.env['res.users'])
        return vendors

    def write(self, vals):
        previous_users = self.user_ids if 'user_ids' in vals else self.env['res.users']
        res = super().write(vals)
        if 'user_ids' in vals:
            self._sync_vendor_portal_group(previous_users)
        if vals.get('active') is False:
            self._withdraw_published_listings()
        return res

    def unlink(self):
        users = self.user_ids
        res = super().unlink()
        self.env['emi.vendor']._sync_vendor_portal_group(users)
        return res

    def _sync_vendor_portal_group(self, previous_users):
        """Add the vendor portal group to linked users and remove it from
        users who are no longer linked to any vendor."""
        group = self.env.ref('emi_marketplace.group_emi_vendor_portal').sudo()
        to_add = self.user_ids - group.user_ids
        candidates = previous_users - self.user_ids
        still_linked = self.sudo().with_context(active_test=False).search(
            [('user_ids', 'in', candidates.ids)]
        ).user_ids if candidates else self.env['res.users']
        to_remove = candidates - still_linked
        commands = [(4, u.id) for u in to_add] + [(3, u.id) for u in to_remove]
        if commands:
            group.write({'user_ids': commands})

    # ------------------------------------------------------------------
    # Workflow
    # ------------------------------------------------------------------

    def _check_marketplace_admin(self):
        if not self.env.su and not self.env.user.has_group('emi_marketplace.group_emi_marketplace_admin'):
            raise AccessError("Only a Marketplace Admin can change a vendor's approval status.")

    def _withdraw_published_listings(self):
        """Send a vendor's live listings back to review when the vendor
        stops being approved, so customers cannot apply for them."""
        self.sudo().product_ids.filtered(
            lambda p: p.listing_state == 'published'
        ).write({'listing_state': 'pending_review'})

    def action_submit(self):
        self._check_marketplace_admin()
        for rec in self:
            if rec.state != 'draft':
                raise UserError("Only draft vendors can be submitted for review.")
            if not rec.sudo().onboarding_document_ids:
                raise UserError("Upload the vendor's onboarding (KYB) documents before submitting.")
            if not rec.settlement_bank_account_id:
                raise UserError("Set the vendor's payout bank account before submitting.")
        self.sudo().write({'state': 'pending'})

    def action_approve(self):
        self._check_marketplace_admin()
        for rec in self:
            if rec.state not in ('pending', 'suspended'):
                raise UserError("Only vendors pending review or suspended can be approved.")
        self.sudo().write({'state': 'approved'})

    def action_reject(self):
        self._check_marketplace_admin()
        for rec in self:
            if rec.state != 'pending':
                raise UserError("Only vendors pending review can be rejected.")
        self.sudo().write({'state': 'rejected'})

    def action_suspend(self):
        self._check_marketplace_admin()
        for rec in self:
            if rec.state != 'approved':
                raise UserError("Only approved vendors can be suspended.")
        self.sudo().write({'state': 'suspended'})
        self._withdraw_published_listings()

    def action_reset_draft(self):
        self._check_marketplace_admin()
        for rec in self:
            if rec.state != 'rejected':
                raise UserError("Only rejected vendors can be reset to draft.")
        self.sudo().write({'state': 'draft'})

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
