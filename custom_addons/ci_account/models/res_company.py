# -*- coding: utf-8 -*-
from odoo import api, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    @api.model_create_multi
    def create(self, vals_list):
        companies = super().create(vals_list)
        companies._ci_account_setup_company()
        return companies

    def _ci_account_setup_company(self):
        """Hook: create the per-company defaults of every ci_account feature
        (follow-up levels, ...). Called on install and on company creation."""
        return True
