# -*- coding: utf-8 -*-
from odoo import models
from odoo.exceptions import UserError


class ResCompany(models.Model):
    _inherit = 'res.company'

    def write(self, vals):
        if 'emi_is_marketplace' in vals and not vals['emi_is_marketplace']:
            # Applications, their entries and retailer collections stay in the old company's books.
            for company in self.filtered('emi_is_marketplace'):
                if self.env['emi.application'].sudo().search_count([('company_id', '=', company.id)], limit=1):
                    raise UserError(
                        f"{company.name} already has EMI applications, which stay with it. Delete them "
                        "(reject submitted ones first) before moving the marketplace to another company."
                    )
        return super().write(vals)
