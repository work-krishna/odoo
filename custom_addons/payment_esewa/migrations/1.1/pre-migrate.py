# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo.addons.payment_esewa import const


def migrate(cr, version):
    # The eSewa public test merchant used to be shipped as data and copied to every
    # company's provider: drop it from the providers nobody switched on.
    cr.execute("""
        UPDATE payment_provider
           SET esewa_product_code = NULL, esewa_secret_key = NULL
         WHERE code = 'esewa' AND state = 'disabled'
           AND esewa_product_code = %s AND esewa_secret_key = %s
    """, [const.TEST_PRODUCT_CODE, const.TEST_SECRET_KEY])
    # transaction_uuid becomes unique: older ones were derived from the reference and
    # could collide. Keep the first transaction of each uuid. The unique index replaces
    # the plain one.
    cr.execute("DROP INDEX IF EXISTS payment_transaction__esewa_transaction_uuid_index")
    cr.execute("""
        UPDATE payment_transaction tx
           SET esewa_transaction_uuid = NULL
         WHERE esewa_transaction_uuid IS NOT NULL
           AND EXISTS (SELECT 1 FROM payment_transaction other
                        WHERE other.esewa_transaction_uuid = tx.esewa_transaction_uuid AND other.id < tx.id)
    """)
