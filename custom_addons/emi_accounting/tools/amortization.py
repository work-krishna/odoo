# -*- coding: utf-8 -*-
"""EMI amortization.

Both interest methods produce a schedule with a constant monthly
installment. The principal/interest split always uses a monthly rate on
the outstanding balance:

* reducing balance: the quoted annual rate / 12;
* flat rate: the effective interest rate (the monthly IRR of the flat EMI
  stream), so interest income follows NFRS 9's effective interest method
  while the customer still pays the flat EMI and the flat total interest.
"""
from dateutil.relativedelta import relativedelta


def flat_effective_monthly_rate(principal, emi, months, tolerance=1e-12):
    """Monthly rate r such that the present value of ``months`` payments
    of ``emi`` at r equals ``principal`` (bisection; the PV is monotonic)."""
    if emi * months <= principal:
        return 0.0

    def present_value(rate):
        return emi * (1 - (1 + rate) ** -months) / rate

    low, high = 1e-12, 1.0
    while present_value(high) > principal:
        high *= 2
    for _i in range(200):
        mid = (low + high) / 2
        if present_value(mid) > principal:
            low = mid
        else:
            high = mid
        if high - low < tolerance:
            break
    return (low + high) / 2


def build_schedule(principal, annual_rate, months, method, start_date, round_fn=None):
    """Return a list of installments (dicts) for a loan disbursed on
    ``start_date``; the first installment is due one month later.

    ``round_fn`` rounds money (e.g. ``currency.round``); the last
    installment absorbs rounding so principal repaid equals ``principal``
    and, for flat loans, total interest equals the quoted flat interest.
    """
    round_fn = round_fn or (lambda amount: round(amount, 2))
    if principal <= 0 or months <= 0:
        return []

    if not annual_rate:
        monthly_rate = 0.0
        emi = principal / months
        total_payable = principal
    elif method == 'reducing':
        monthly_rate = annual_rate / 100.0 / 12.0
        factor = (1 + monthly_rate) ** months
        emi = principal * monthly_rate * factor / (factor - 1)
        total_payable = None  # whatever the rounded schedule adds up to
    else:
        total_interest = principal * annual_rate / 100.0 * months / 12.0
        total_payable = principal + total_interest
        emi = total_payable / months
        monthly_rate = flat_effective_monthly_rate(principal, emi, months)

    emi = round_fn(emi)
    balance = round_fn(principal)
    lines, paid_so_far = [], 0.0
    for number in range(1, months + 1):
        opening = balance
        if number < months:
            interest = round_fn(opening * monthly_rate)
            principal_part = round_fn(emi - interest)
            amount = emi
        else:
            principal_part = opening
            if total_payable is None:
                interest = round_fn(opening * monthly_rate)
                amount = round_fn(principal_part + interest)
            else:
                amount = round_fn(total_payable - paid_so_far)
                interest = round_fn(amount - principal_part)
        balance = round_fn(opening - principal_part)
        paid_so_far += amount
        lines.append({
            'number': number,
            'due_date': start_date + relativedelta(months=number),
            'opening_balance': opening,
            'amount': amount,
            'principal_amount': principal_part,
            'interest_amount': interest,
            'closing_balance': balance,
        })
    return lines
