# -*- coding: utf-8 -*-
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    """res_company_data.xml is noupdate, so databases upgrading from 1.0
    never get the marketplace flag: set it on the main company."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    Company = env['res.company']
    if not Company.search_count([('emi_is_marketplace', '=', True)]):
        main = env.ref('base.main_company', raise_if_not_found=False)
        if main and not env['emi.finance.company'].search_count([('company_id', '=', main.id)]):
            main.emi_is_marketplace = True
