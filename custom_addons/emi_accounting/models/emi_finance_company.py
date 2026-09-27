# -*- coding: utf-8 -*-
from odoo import fields, models

DOWN_PAYMENT_RECEIVERS = [
    ('retailer', 'Retailer'),
    ('marketplace', 'Marketplace'),
    ('finance_company', 'Finance Company'),
]


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
    down_payment_collection = fields.Selection(
        DOWN_PAYMENT_RECEIVERS, string='Down Payment Received By', required=True, default='marketplace',
        help="Who takes the customer's down payment on this finance company's loans (each application can "
             "still change it until a down payment is recorded). Retailer: paid at the shop and only "
             "confirmed here, so the marketplace holds just the financed amount for the retailer. "
             "Marketplace: received on the retailer's behalf. Finance company: received in its own books, "
             "and it pays the marketplace the full price at disbursement.",
    )
