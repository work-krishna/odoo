from . import controllers
from . import models


def _post_init_hook(env):
    websites = env['website'].search([])
    for fname in ('favicon', 'has_company_favicon'):
        env.add_to_compute(websites._fields[fname], websites)
    websites.flush_recordset(['favicon', 'has_company_favicon'])
