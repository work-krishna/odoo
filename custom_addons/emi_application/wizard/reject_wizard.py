# -*- coding: utf-8 -*-
from odoo import fields, models


class EmiApplicationRejectWizard(models.TransientModel):
    _name = 'emi.application.reject.wizard'
    _description = 'Reject EMI Application'

    application_id = fields.Many2one('emi.application', required=True, ondelete='cascade')
    reason = fields.Text(required=True)

    def action_confirm(self):
        self.ensure_one()
        self.application_id.action_reject(self.reason)
        return {'type': 'ir.actions.act_window_close'}
