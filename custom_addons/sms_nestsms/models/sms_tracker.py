# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging
from datetime import timedelta

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

STATUS_WINDOW = timedelta(days=2)  # after that a text stays "Sent"


class SmsTracker(models.Model):
    _inherit = 'sms.tracker'

    sms_nestsms_message_id = fields.Char(
        string="NestSMS Message ID", readonly=True, index='btree_not_null',
        help="NestSMS's id for this SMS, used to look up its delivery status.",
    )

    @api.model
    def _nestsms_cron_update_delivery(self, limit=200):
        """Ask NestSMS what became of recent texts still shown as Sent, and mark them
        Delivered or Failed on their chatter."""
        trackers = self.search([
            ('sms_nestsms_message_id', '!=', False),
            ('mail_notification_id.notification_status', '=', 'pending'),
            ('create_date', '>=', fields.Datetime.now() - STATUS_WINDOW),
        ], order='id', limit=limit)
        apis = {}
        for tracker in trackers:
            company = tracker.mail_notification_id.mail_message_id.record_company_id or self.env.company
            if company not in apis:
                apis[company] = company._sms_nestsms_api()
            reply = apis[company]._nestsms_get_status(tracker.sms_nestsms_message_id)
            if not reply.ok:
                if reply.stops_batch:  # bad key, NestSMS down...: try again next run
                    _logger.info("NestSMS delivery status: stopped, %s", reply.reason)
                    break
                continue
            status = reply.data.get('status')
            if status == 'delivered':
                tracker._action_update_from_sms_state('sent')
            elif status == 'failed':
                tracker.with_context(
                    sms_known_failure_reason=reply.data.get('error_message') or reply.data.get('error_code'),
                )._action_update_from_provider_error('not_delivered')
