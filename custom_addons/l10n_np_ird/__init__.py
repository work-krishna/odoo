from . import models
from . import tools
from . import wizard


def _l10n_np_ird_post_init(env):
    """Turn on IRD fiscal-year numbering for companies already set up for Nepal."""
    companies = env['res.company'].search([('account_fiscal_country_id.code', '=', 'NP')])
    companies.l10n_np_bs_invoice_numbering = True
