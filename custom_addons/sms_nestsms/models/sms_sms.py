# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import models


class SmsSms(models.Model):
    _inherit = 'sms.sms'

    def _split_by_api(self):
        # Core hands the whole queue to Odoo IAP, an international route that NTA rules
        # forbid for this account. Send each company's SMS through its NestSMS account instead.
        for company, sms in self.grouped(lambda s: s._get_sms_company()).items():
            sms_api = company._get_sms_api_class()(self.env)
            sms_api._set_company(company)
            yield sms_api, sms

    def _get_send_batch_size(self):
        # One HTTP call per SMS, so keep each cron batch short.
        return int(self.env['ir.config_parameter'].sudo().get_param('sms_nestsms.session.batch.size', 50))

    def _handle_call_result_hook(self, results):
        # The SMS row is deleted once sent; keep NestSMS's message id on the tracker for
        # delivery-status lookups.
        sms_by_uuid = self.grouped('uuid')
        for result in results:
            sms = sms_by_uuid.get(result.get('uuid'))
            if sms and sms.sms_tracker_id and result.get('nestsms_message_id'):
                sms.sms_tracker_id.sms_nestsms_message_id = result['nestsms_message_id']
        return super()._handle_call_result_hook(results)
