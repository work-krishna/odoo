# -*- coding: utf-8 -*-
from datetime import date, timedelta

from odoo.tests import BaseCase, tagged

from odoo.addons.l10n_np_ird.tools import bs_calendar as bs


@tagged('post_install', '-at_install')
class TestBsCalendar(BaseCase):

    def test_known_dates(self):
        # Nepali New Year (Baisakh 1) and the start of the fiscal year (Shrawan 1).
        self.assertEqual(bs.bs_to_ad(2080, 1, 1), date(2023, 4, 14))
        self.assertEqual(bs.bs_to_ad(2081, 1, 1), date(2024, 4, 13))
        self.assertEqual(bs.bs_to_ad(2082, 1, 1), date(2025, 4, 14))
        self.assertEqual(bs.bs_to_ad(2082, 4, 1), date(2025, 7, 17))
        self.assertEqual(bs.ad_to_bs(date(1918, 4, 13)), (1975, 1, 1))

    def test_round_trip_over_range(self):
        day = bs.bs_to_ad(bs.MIN_YEAR, 1, 1)
        last = bs.bs_to_ad(bs.MAX_YEAR, 12, bs.BS_MONTH_DAYS[bs.MAX_YEAR][11])
        while day <= last:
            self.assertEqual(bs.bs_to_ad(*bs.ad_to_bs(day)), day)
            day += timedelta(days=7)

    def test_fiscal_year(self):
        self.assertEqual(bs.fiscal_year_start(date(2026, 7, 16)), 2082)
        self.assertEqual(bs.fiscal_year_start(date(2026, 7, 17)), 2083)
        self.assertEqual(bs.fiscal_year_bounds(2083), (date(2026, 7, 17), date(2027, 7, 16)))
        self.assertEqual(bs.fiscal_year_label(2083), '2083/84')
        self.assertEqual(bs.cbms_fiscal_year(2083), '2083.084')
        self.assertEqual(bs.format_bs(date(2026, 9, 23)), '2083.06.07')

    def test_out_of_range(self):
        with self.assertRaises(ValueError):
            bs.bs_to_ad(2101, 1, 1)
        with self.assertRaises(ValueError):
            bs.bs_to_ad(2083, 3, 33)
