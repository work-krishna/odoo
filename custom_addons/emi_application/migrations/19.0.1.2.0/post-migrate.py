# -*- coding: utf-8 -*-
from odoo import SUPERUSER_ID, api

LATER_STATES = ('pending_finance_approval', 'approved', 'disbursed', 'active', 'closed', 'defaulted')


def migrate(cr, version):
    """Finance reviewers now only see applications sent to them
    (sent_to_finance_date). Fill it for applications that already reached
    the lender: every state after KYC review, and rejections the lender made
    (sending is the only way into Pending Finance Approval, so a tracked move
    there identifies them and gives the date)."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    state_field = env['emi.application']._fields['state']
    labels = tuple({
        dict(state_field._description_selection(env(context={'lang': code})))['pending_finance_approval']
        for code, _name in env['res.lang'].get_installed()
    })
    cr.execute("""
        SELECT m.res_id, MIN(m.date)
          FROM mail_tracking_value v
          JOIN mail_message m ON m.id = v.mail_message_id
          JOIN ir_model_fields f ON f.id = v.field_id
         WHERE m.model = 'emi.application' AND f.model = 'emi.application' AND f.name = 'state'
           AND v.new_value_char IN %s
         GROUP BY m.res_id
    """, [labels])
    for app_id, date in cr.fetchall():
        cr.execute("""
            UPDATE emi_application SET sent_to_finance_date = %s
             WHERE id = %s AND sent_to_finance_date IS NULL AND state IN %s
        """, [date, app_id, LATER_STATES + ('rejected',)])
    cr.execute("""
        UPDATE emi_application SET sent_to_finance_date = write_date
         WHERE sent_to_finance_date IS NULL AND state IN %s
    """, [LATER_STATES])
