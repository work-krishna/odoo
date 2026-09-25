# -*- coding: utf-8 -*-


def migrate(cr, version):
    """Listings saved with a NaN or infinite price make every page showing
    them fail. Clear the price and take published ones off the storefront
    until the retailer enters a real one."""
    cr.execute("""
        UPDATE product_template
           SET list_price = 0,
               listing_state = CASE WHEN listing_state = 'published' THEN 'draft' ELSE listing_state END
         WHERE vendor_id IS NOT NULL
           AND list_price::float8 IN ('NaN'::float8, 'Infinity'::float8, '-Infinity'::float8)
    """)
