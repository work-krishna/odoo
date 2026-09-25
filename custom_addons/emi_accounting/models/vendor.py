# -*- coding: utf-8 -*-
from odoo import fields, models
from odoo.exceptions import UserError
from odoo.fields import Domain


class EmiVendor(models.Model):
    _inherit = 'emi.vendor'

    settlement_ids = fields.One2many('emi.vendor.settlement', 'vendor_id', string='Settlements')
    marketplace_company_id = fields.Many2one(
        'res.company', string='Marketplace Company', compute='_compute_marketplace_company_id',
        search='_search_marketplace_company_id',
        help="Retailers sell through the marketplace company; used to limit accountants to its retailers.",
    )

    def _compute_marketplace_company_id(self):
        self.marketplace_company_id = self.env['res.company']._emi_get_marketplace_company()

    def _search_marketplace_company_id(self, operator, value):
        if operator != 'in':
            return NotImplemented
        marketplace = self.env['res.company']._emi_get_marketplace_company()
        return Domain.TRUE if marketplace.id in value else Domain.FALSE

    def action_create_settlement(self):
        self.ensure_one()
        settlement = self.env['emi.vendor.settlement']._create_for_vendor(self)
        if not settlement:
            raise UserError(f"Nothing has been collected for {self.name} yet.")
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'emi.vendor.settlement',
            'res_id': settlement.id,
            'view_mode': 'form',
        }
