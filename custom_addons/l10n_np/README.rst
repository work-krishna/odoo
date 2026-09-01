.. image:: https://img.shields.io/badge/license-LGPL--3-green.svg
    :target: https://www.gnu.org/licenses/lgpl-3.0-standalone.html
    :alt: License: LGPL-3

Nepal - Accounting
===================
Nepal fiscal localization for Odoo 19 Accounting: Chart of Accounts, VAT
(13%) tax templates, Domestic/Export fiscal positions, TDS (Tax Deducted at
Source) withholding taxes, and a Nepal VAT Report wizard.

.. IMPORTANT::
   The chart of accounts and all VAT/TDS rates in this module are based on
   publicly documented Nepal tax rules, provided as a v1 starting point.
   They are **not** an official or certified IRD format. Verify against the
   current Finance Act and IRD notifications, and consult a qualified
   Nepali accountant, before production use.

Configuration
=============
Create a new company (or set an existing company's country) to **Nepal**
and run the Accounting onboarding, or install this module directly and use
*Accounting ‣ Configuration ‣ Chart of Accounts ‣ Load* to load the "Nepal"
chart template.

Usage
=====
* **Chart of Accounts**: Accounting ‣ Configuration ‣ Chart of Accounts
* **Taxes** (VAT 13%/0%, TDS rates): Accounting ‣ Configuration ‣ Taxes
* **Fiscal Positions** (Domestic / Export): Accounting ‣ Configuration ‣
  Fiscal Positions
* **TDS on vendor payments**: add the relevant TDS tax to a vendor bill
  line's taxes alongside VAT, then use *Register Payment* - the withheld
  amount is computed and posted automatically when the payment is
  registered (not at bill validation time).
* **Nepal VAT Report**: Accounting ‣ Reporting ‣ Statement Reports ‣ Nepal
  VAT Report

Company
-------
* Krishna Kumar Sah

License
-------
General Public License, Version 3 (LGPL v3).
https://www.gnu.org/licenses/lgpl-3.0-standalone.html

Credits
-------
* Developer: Krishna Kumar Sah
