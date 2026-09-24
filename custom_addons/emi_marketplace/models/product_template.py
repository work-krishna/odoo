# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    vendor_id = fields.Many2one(
        'emi.vendor', string='Vendor', ondelete='restrict', index=True,
        help="Marketplace vendor who owns and is paid out for this listing.",
    )
    listing_state = fields.Selection(
        [
            ('draft', 'Draft'),
            ('pending_review', 'Pending Review'),
            ('published', 'Published'),
            ('rejected', 'Rejected'),
        ],
        default='draft', required=True, tracking=True, copy=False,
        help="Marketplace moderation status. Only 'published' listings appear on the storefront.",
    )

    @api.constrains('listing_state', 'vendor_id')
    def _check_published_vendor(self):
        for rec in self:
            if rec.listing_state == 'published' and rec.vendor_id.state != 'approved':
                raise ValidationError(
                    f"{rec.display_name} cannot be published: its vendor is not approved."
                )

    def _is_marketplace_admin(self):
        return self.env.su or self.env.user.has_group('emi_marketplace.group_emi_marketplace_admin')

    @api.model_create_multi
    def create(self, vals_list):
        if not self._is_marketplace_admin() and any(
            vals.get('listing_state', 'draft') != 'draft' for vals in vals_list
        ):
            raise AccessError("New listings start as drafts; only a Marketplace Admin can set another status.")
        return super().create(vals_list)

    def write(self, vals):
        if 'listing_state' in vals and not self._is_marketplace_admin():
            raise AccessError("Only a Marketplace Admin can change a listing's moderation status.")
        if 'vendor_id' in vals and not self.env.su and any(
            rec.listing_state == 'published' and rec.vendor_id.id != vals['vendor_id'] for rec in self
        ):
            raise UserError("Unpublish a listing before moving it to another vendor.")
        return super().write(vals)

    def action_submit_listing(self):
        for rec in self:
            if not rec.vendor_id:
                raise UserError("A product must have a vendor before it can be submitted for review.")
            if not (rec._is_marketplace_admin() or self.env.user in rec.vendor_id.sudo().user_ids):
                raise AccessError("Only the vendor's own users or a Marketplace Admin can submit this listing.")
            if rec.vendor_id.sudo().state != 'approved':
                raise UserError("The vendor must be approved before its listings can be submitted.")
            if rec.listing_state != 'draft':
                raise UserError("Only draft listings can be submitted for review.")
        self.sudo().write({'listing_state': 'pending_review'})

    def action_publish_listing(self):
        if not self._is_marketplace_admin():
            raise AccessError("Only a Marketplace Admin can publish listings.")
        for rec in self:
            if rec.listing_state != 'pending_review':
                raise UserError("Only listings pending review can be published.")
            if rec.vendor_id.state != 'approved':
                raise UserError("This vendor is not approved -- their listings cannot be published.")
        self.write({'listing_state': 'published'})

    def action_reject_listing(self):
        if not self._is_marketplace_admin():
            raise AccessError("Only a Marketplace Admin can reject listings.")
        for rec in self:
            if rec.listing_state != 'pending_review':
                raise UserError("Only listings pending review can be rejected.")
        self.write({'listing_state': 'rejected'})

    def action_unpublish_listing(self):
        if not self._is_marketplace_admin():
            raise AccessError("Only a Marketplace Admin can unpublish listings.")
        for rec in self:
            if rec.listing_state != 'published':
                raise UserError("Only published listings can be unpublished.")
        self.write({'listing_state': 'draft'})

    def action_reset_listing_draft(self):
        for rec in self:
            if not (rec._is_marketplace_admin() or self.env.user in rec.vendor_id.sudo().user_ids):
                raise AccessError("Only the vendor's own users or a Marketplace Admin can reopen this listing.")
            if rec.listing_state != 'rejected':
                raise UserError("Only rejected listings can be reset to draft.")
        self.sudo().write({'listing_state': 'draft'})
