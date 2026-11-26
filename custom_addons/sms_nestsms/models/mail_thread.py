# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging

from odoo import models

from odoo.addons.sms_nestsms.tools.sms_api import nepal_mobile

_logger = logging.getLogger(__name__)


class MailThread(models.AbstractModel):
    _inherit = 'mail.thread'

    def _sms_nestsms_notify(self, template, partner):
        """Queue a transactional SMS to `partner` from `template` (an sms.template or its XML
        id), logged on this record's chatter. The SMS cron sends it right after the commit,
        so the business flow never waits on NestSMS.

        Skips (returns False) when it can't or shouldn't send: the record's company has no
        NestSMS key yet, the partner has no Nepali mobile number, or the number opted out
        (phone blacklist). Never raises: an SMS problem must not block an order, payment
        or delivery.
        """
        self.ensure_one()
        record = self.sudo()
        company = record.company_id if 'company_id' in record._fields and record.company_id else self.env.company
        if isinstance(template, str):
            template = self.env.ref(template, raise_if_not_found=False)
        partner = partner.sudo()
        if not template or not partner or not company.sudo().sms_nestsms_api_key:
            return False
        mobile = nepal_mobile(partner.phone_sanitized or partner.phone)
        if not mobile:
            _logger.info("No SMS %s for %s %s: %s has no Nepali mobile number.",
                         template.display_name, self._name, self.id, partner.display_name)
            return False
        number = '+977' + mobile
        if self.env['phone.blacklist'].sudo().search_count([('number', '=', number)], limit=1):
            return False
        try:
            with self.env.cr.savepoint():
                record.with_company(company)._message_sms_with_template(
                    template=template.sudo(),
                    partner_ids=partner.ids,
                    sms_pid_to_number={partner.id: number},
                    author_id=self.env.ref('base.partner_root').id,
                    put_in_queue=True,
                )
        except Exception:
            _logger.exception("Could not queue SMS %s for %s %s", template.display_name, self._name, self.id)
            return False
        return True
