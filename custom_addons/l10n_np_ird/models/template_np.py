# -*- coding: utf-8 -*-
from odoo import models
from odoo.addons.account.models.chart_template import template


class AccountChartTemplate(models.AbstractModel):
    _inherit = 'account.chart.template'

    @template('np', 'res.company')
    def _get_np_ird_res_company(self):
        return {
            self.env.company.id: {
                'l10n_np_bs_invoice_numbering': True,
            },
        }
