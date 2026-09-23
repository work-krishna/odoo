# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import UserError


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
        default='draft', required=True, tracking=True,
        help="Marketplace moderation status. Only 'published' listings appear on the storefront.",
    )

    def action_submit_listing(self):
        for rec in self:
            if not rec.vendor_id:
                raise UserError("A product must have a vendor before it can be submitted for review.")
            if rec.listing_state != 'draft':
                raise UserError("Only draft listings can be submitted for review.")
            rec.listing_state = 'pending_review'

    def action_publish_listing(self):
        for rec in self:
            if rec.listing_state != 'pending_review':
                raise UserError("Only listings pending review can be published.")
            if rec.vendor_id.state != 'approved':
                raise UserError("This vendor is not approved -- their listings cannot be published.")
            rec.listing_state = 'published'

    def action_reject_listing(self):
        for rec in self:
            if rec.listing_state != 'pending_review':
                raise UserError("Only listings pending review can be rejected.")
            rec.listing_state = 'rejected'
