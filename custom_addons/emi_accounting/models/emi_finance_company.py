# -*- coding: utf-8 -*-
from odoo import fields, models


class EmiFinanceCompany(models.Model):
    _inherit = 'emi.finance.company'

    installment_collection = fields.Selection(
        [
            ('finance_company', 'Finance company collects'),
            ('marketplace', 'Marketplace collects and remits'),
        ],
        string='Installment Collection', required=True, default='finance_company',
        help="Who receives the customer's monthly installments. When the marketplace "
             "collects, each receipt is booked as payable to this finance company in the "
             "marketplace's books and remitted later.",
    )
