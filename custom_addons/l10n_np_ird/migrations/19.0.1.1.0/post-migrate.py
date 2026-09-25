# -*- coding: utf-8 -*-
from odoo import SUPERUSER_ID, api

from odoo.addons.l10n_np_ird.models.account_move import CBMS_REJECTED_CODES


def migrate(cr, version):
    """Queued invoices may already be at IRD: an earlier send timed out, or a cron batch
    rolled back after posting them. Record their current version as possibly held, so
    they stay locked and a code 101 on the retry still confirms them."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    moves = env['account.move'].search([
        ('l10n_np_cbms_state', 'in', ('to_send', 'error')),
        ('state', '=', 'posted'),
        ('move_type', 'in', ('out_invoice', 'out_refund')),
        ('company_id.l10n_np_cbms_enabled', '=', True),
    ])
    rejected = tuple(f"{code}:" for code in CBMS_REJECTED_CODES)
    for move in moves:
        if (move.l10n_np_cbms_response or '').startswith(rejected):
            continue  # IRD answered and did not store it
        move.l10n_np_cbms_fingerprints = move._l10n_np_cbms_fingerprint(move._l10n_np_cbms_payload(False))
