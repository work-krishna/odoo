# -*- coding: utf-8 -*-
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    """19.0.1.4.0 kept extra KYC items (KYC Requirements) in emi.kyc.item, now
    removed. A signed application form uploaded there becomes the application's
    EMI Application Form; the other leftovers are cleared before the upgrade
    drops the two tables."""
    cr.execute("SELECT to_regclass('emi_kyc_item')")
    if not cr.fetchone()[0]:
        return
    cr.execute("""
        SELECT res_id FROM ir_model_data
         WHERE module = 'emi_application' AND name = 'kyc_requirement_signed_agreement'
    """)
    row = cr.fetchone()
    if row:
        # Re-link the stored file rather than copying it.
        cr.execute("""
            UPDATE ir_attachment att
               SET res_model = 'emi.application', res_field = 'application_form',
                   res_id = kyc.application_id, name = 'application_form'
              FROM emi_kyc_item item
              JOIN emi_kyc kyc ON kyc.id = item.kyc_id
             WHERE att.res_model = 'emi.kyc.item' AND att.res_field = 'value_file' AND att.res_id = item.id
               AND item.requirement_id = %s
               AND NOT EXISTS (
                   SELECT 1 FROM ir_attachment other
                    WHERE other.res_model = 'emi.application' AND other.res_field = 'application_form'
                      AND other.res_id = kyc.application_id
               )
         RETURNING att.res_id
        """, [row[0]])
        moved = [res_id for (res_id,) in cr.fetchall()]
        if moved:
            cr.execute("""
                UPDATE emi_application app
                   SET application_form_filename = item.value_filename
                  FROM emi_kyc_item item
                  JOIN emi_kyc kyc ON kyc.id = item.kyc_id
                 WHERE kyc.application_id = app.id AND item.requirement_id = %s AND app.id = ANY(%s)
            """, [row[0], moved])
    env = api.Environment(cr, SUPERUSER_ID, {})
    env['ir.attachment'].search([
        ('res_model', 'in', ('emi.kyc.item', 'emi.kyc.requirement')), ('res_field', '!=', False),
    ]).unlink()
    # The seeded item was noupdate data, which the upgrade itself would leave behind.
    cr.execute("DELETE FROM ir_model_data WHERE model IN ('emi.kyc.item', 'emi.kyc.requirement')")
    # Odoo removes the models' metadata but cannot drop tables of models no longer in the code.
    cr.execute("DROP TABLE IF EXISTS emi_kyc_item, emi_kyc_requirement CASCADE")
