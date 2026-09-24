# -*- coding: utf-8 -*-
from odoo import fields, models
from odoo.exceptions import UserError


class EmiVendor(models.Model):
    _inherit = 'emi.vendor'

    settlement_ids = fields.One2many('emi.vendor.settlement', 'vendor_id', string='Settlements')

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
