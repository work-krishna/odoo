# -*- coding: utf-8 -*-
"""Bikram Sambat (BS) calendar helpers and the Nepali fiscal year.

The Nepali fiscal year runs from Shrawan 1 (BS month 4) to the last day
of Asar (BS month 3) of the next BS year. FY "2083/84" therefore starts
on Shrawan 1, 2083 and ends on the last day of Asar 2084.
"""
from datetime import date, timedelta
from itertools import accumulate

from .bs_calendar_data import BS_MONTH_DAYS

MIN_YEAR = min(BS_MONTH_DAYS)
MAX_YEAR = max(BS_MONTH_DAYS)
# A fiscal year ends in the next BS year, so the last full one is FY 2099/00.
MAX_FISCAL_YEAR = MAX_YEAR - 1
REFERENCE_AD = date(1918, 4, 13)  # == BS MIN_YEAR-01-01
FISCAL_YEAR_START_MONTH = 4  # Shrawan

MONTH_NAMES = (
    'Baisakh', 'Jestha', 'Asar', 'Shrawan', 'Bhadra', 'Asoj',
    'Kartik', 'Mangsir', 'Poush', 'Magh', 'Falgun', 'Chaitra',
)

# Days elapsed before the start of each BS year, counted from REFERENCE_AD.
_YEARS = sorted(BS_MONTH_DAYS)
_DAYS_BEFORE_YEAR = dict(zip(_YEARS, accumulate((sum(BS_MONTH_DAYS[y]) for y in _YEARS), initial=0)))


def _check_year(year):
    if not MIN_YEAR <= year <= MAX_YEAR:
        raise ValueError(f"Bikram Sambat year {year} is outside the supported range {MIN_YEAR}-{MAX_YEAR}.")


def bs_to_ad(year, month, day):
    """Convert a BS date to a Gregorian :class:`datetime.date`."""
    _check_year(year)
    if not 1 <= month <= 12:
        raise ValueError(f"Invalid Bikram Sambat month {month}.")
    if not 1 <= day <= BS_MONTH_DAYS[year][month - 1]:
        raise ValueError(f"{MONTH_NAMES[month - 1]} {year} has {BS_MONTH_DAYS[year][month - 1]} days, not {day}.")
    offset = _DAYS_BEFORE_YEAR[year] + sum(BS_MONTH_DAYS[year][:month - 1]) + day - 1
    return REFERENCE_AD + timedelta(days=offset)


def ad_to_bs(ad_date):
    """Convert a Gregorian date to a ``(year, month, day)`` BS tuple."""
    offset = (ad_date - REFERENCE_AD).days
    if offset < 0:
        raise ValueError(f"{ad_date} is before the supported Bikram Sambat range.")
    for year in _YEARS:
        year_days = sum(BS_MONTH_DAYS[year])
        if offset < year_days:
            for month, month_days in enumerate(BS_MONTH_DAYS[year], start=1):
                if offset < month_days:
                    return year, month, offset + 1
                offset -= month_days
        offset -= year_days
    raise ValueError(f"{ad_date} is after the supported Bikram Sambat range.")


def format_bs(ad_date, sep='.'):
    """'2083.06.07' style BS date string (the format IRD/CBMS expects)."""
    year, month, day = ad_to_bs(ad_date)
    return f"{year:04d}{sep}{month:02d}{sep}{day:02d}"


def fiscal_year_start(ad_date):
    """BS year in which the fiscal year containing ``ad_date`` starts."""
    year, month, _day = ad_to_bs(ad_date)
    return year if month >= FISCAL_YEAR_START_MONTH else year - 1


def fiscal_year_bounds(start_year):
    """Gregorian (first_day, last_day) of the BS fiscal year starting in ``start_year``."""
    if start_year > MAX_FISCAL_YEAR:
        raise ValueError(
            f"Nepali fiscal year {fiscal_year_label(start_year)} ends after the supported "
            f"Bikram Sambat range; the last supported one is {fiscal_year_label(MAX_FISCAL_YEAR)}."
        )
    first = bs_to_ad(start_year, FISCAL_YEAR_START_MONTH, 1)
    last = bs_to_ad(start_year + 1, FISCAL_YEAR_START_MONTH, 1) - timedelta(days=1)
    return first, last


def fiscal_year_label(start_year):
    """Human label, e.g. '2083/84'."""
    return f"{start_year}/{(start_year + 1) % 100:02d}"


def cbms_fiscal_year(start_year):
    """Fiscal year in the CBMS API format, e.g. '2083.084'."""
    return f"{start_year}.{(start_year + 1) % 1000:03d}"
