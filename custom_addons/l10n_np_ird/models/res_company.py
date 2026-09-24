# -*- coding: utf-8 -*-
from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    l10n_np_bs_invoice_numbering = fields.Boolean(
        string='Nepali Fiscal-Year Invoice Numbering',
        help="Number customer invoices and credit notes per Nepali fiscal year "
             "(Shrawan 1 to the end of Asar), e.g. INV/2083-84/0001, as IRD requires.",
    )
    l10n_np_cbms_enabled = fields.Boolean(
        string='Sync Invoices to IRD CBMS',
        help="Send every posted customer invoice and credit note to the IRD Central "
             "Billing Monitoring System.",
    )
    l10n_np_cbms_url = fields.Char(
        string='CBMS API URL', default='https://cbapi.ird.gov.np',
        help="Base URL of the CBMS API. Use the test URL IRD gave you while testing.",
    )
    l10n_np_cbms_username = fields.Char(string='CBMS Username', groups='base.group_system')
    l10n_np_cbms_password = fields.Char(string='CBMS Password', groups='base.group_system')
