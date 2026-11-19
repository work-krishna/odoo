# Part of Odoo. See LICENSE file for full copyright and licensing details.

from markupsafe import Markup

from odoo import _, fields, models
from odoo.exceptions import UserError

from odoo.addons.delivery_ncm.models.ncm_request import NcmError


class NcmCommentWizard(models.TransientModel):
    _name = 'ncm.comment.wizard'
    _description = "Message Nepal Can Move"

    picking_id = fields.Many2one('stock.picking', required=True, ondelete='cascade')
    ncm_order_id = fields.Integer(related='picking_id.ncm_order_id')
    message = fields.Text(required=True)

    def action_send(self):
        self.ensure_one()
        text = (self.message or '').strip()
        picking = self.picking_id
        if not text:
            raise UserError(_("Write a message first."))
        if not picking.ncm_order_id:
            raise UserError(_("This transfer has no NCM order yet."))
        try:
            picking.carrier_id._ncm_client().post_comment(picking.ncm_order_id, text)
        except NcmError as e:
            # NCM accepts at most one comment per order per minute.
            raise UserError(_("NCM did not accept the message: %s", e.message)) from e
        picking.message_post(
            body=Markup("<b>%s</b><br/>%s") % (_("Sent to NCM:"), text),
            subtype_xmlid='mail.mt_note',
        )
        return {'type': 'ir.actions.act_window_close'}
