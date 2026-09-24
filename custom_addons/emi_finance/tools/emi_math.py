# -*- coding: utf-8 -*-
"""EMI quote shown to customers (application preview, storefront calculator).

The authoritative installment schedule is built by emi_accounting; this is
the headline monthly EMI and total cost for a principal, annual rate,
tenure and interest method.
"""


def quote(principal, annual_rate, months, method):
    """Return {'emi', 'total_interest', 'total_payable'} (unrounded)."""
    if not principal or not months:
        return {'emi': 0.0, 'total_interest': 0.0, 'total_payable': 0.0}
    if not annual_rate:
        emi = principal / months
        total_interest = 0.0
    elif method == 'reducing':
        monthly_rate = annual_rate / 100.0 / 12.0
        factor = (1 + monthly_rate) ** months
        emi = principal * monthly_rate * factor / (factor - 1)
        total_interest = emi * months - principal
    else:  # flat
        total_interest = principal * annual_rate / 100.0 * months / 12.0
        emi = (principal + total_interest) / months
    return {'emi': emi, 'total_interest': total_interest, 'total_payable': principal + total_interest}
