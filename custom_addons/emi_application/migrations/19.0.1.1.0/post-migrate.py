# -*- coding: utf-8 -*-
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    """interest_rate_id became a stored compute; the column already existed,
    so the ORM does not fill it for old drafts (their rate was never saved
    by the form). Resolve it so the EMI preview is right before submission."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    Rate = env['emi.interest.rate']
    for app in env['emi.application'].search([('state', '=', 'draft')]):
        rate = Rate.get_active_rate(app.finance_company_id.id, app.tenure_plan_id.id)
        app.write({
            'interest_rate_id': rate.id,
            'interest_rate_percent': rate.rate_percent,
            'interest_calc_method': rate.calc_method,
        })
