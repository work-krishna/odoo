# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import ValidationError


class ResCompany(models.Model):
    _inherit = 'res.company'

    emi_is_marketplace = fields.Boolean(
        string='EMI Marketplace Company',
        help="The company that runs the EMI marketplace: it owns the phone catalog, "
             "takes the applications and invoices the finance companies. Only one "
             "company can hold this flag, and it cannot also be a finance company.",
    )

    @api.constrains('emi_is_marketplace')
    def _check_single_emi_marketplace(self):
        if self.sudo().search_count([('emi_is_marketplace', '=', True)]) > 1:
            raise ValidationError("Only one company can be the EMI marketplace company.")
        flagged = self.filtered('emi_is_marketplace')
        if flagged and self.env['emi.finance.company'].sudo().with_context(active_test=False).search_count(
            [('company_id', 'in', flagged.ids)], limit=1,
        ):
            raise ValidationError(
                "A finance company cannot also be the EMI marketplace company; flag a separate company."
            )

    @api.model
    def _emi_get_marketplace_company(self):
        """Return the flagged marketplace company, falling back to the main company."""
        company = self.sudo().search([('emi_is_marketplace', '=', True)], limit=1)
        return company or self.env.ref('base.main_company', raise_if_not_found=False) or self.browse()
