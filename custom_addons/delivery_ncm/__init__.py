# Part of Odoo. See LICENSE file for full copyright and licensing details.

from . import controllers
from . import models
from . import wizard


def post_init_hook(env):
    """Fetch NCM's branch list in the background right after install."""
    env.ref('delivery_ncm.ir_cron_ncm_sync_branches')._trigger()
