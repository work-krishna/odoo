# -*- coding: utf-8 -*-
from odoo import api, models
from odoo.exceptions import UserError


class AccountResequenceWizard(models.TransientModel):
    _inherit = 'account.resequence.wizard'

    @api.model
    def _l10n_np_check_moves(self, moves):
        # The wizard groups moves by the company's Gregorian fiscal year, which does not
        # match the BS fiscal years in the names: it would duplicate or misdate numbers.
        bs_numbered = moves.filtered(lambda m: m._l10n_np_bs_numbering())
        if bs_numbered:
            raise UserError(
                f"Journal {bs_numbered.journal_id[:1].display_name} is numbered per Nepali fiscal year, "
                "which the resequence tool does not support."
            )

    @api.model
    def default_get(self, fields):
        values = super().default_get(fields)
        if values.get('move_ids'):
            self._l10n_np_check_moves(self.env['account.move'].browse(values['move_ids'][0][2]))
        return values

    def resequence(self):
        self._l10n_np_check_moves(self.move_ids)
        return super().resequence()
