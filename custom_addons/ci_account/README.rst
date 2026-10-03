=============
CI Accounting
=============

``ci_account`` turns the Community *Invoicing* app into a full *Accounting* app
(the features of the Enterprise ``accountant`` modules), and is the single
accounting base the other Chaitanya Innovation modules build on. It depends
only on ``account`` and works with any chart of accounts; with ``l10n_np`` /
``l10n_np_ird`` it follows the Nepali fiscal year.

.. contents::
   :local:

Access rights
=============

Settings > Users > *Accounting* now offers four roles:

* **Invoicing**: invoices, bills, payments, follow-ups.
* **Auditor (Read-only)**: sees all journal entries, reports and configuration, changes nothing.
* **Accountant**: Invoicing + journal entries, bank reconciliation, assets, budgets and every report.
* **Administrator**: Accountant + configuration, lock dates and closing.

The app menu is renamed *Accounting*. Uninstalling the module gives Community its
*Invoicing* menu and hidden groups back.

Chart of accounts
=================

* Accounting > Chart of Accounts (also under Configuration > Accounting), with
  opening balances.
* Configuration > Accounting > **Account Groups** (code-prefix hierarchy used by
  the trial balance) and **Account Tags** (the *Operating / Investing / Financing
  Activity* tags place accounts in the cash flow statement).

Financial reports
=================

Reporting menu, each with dates, comparison periods, journal / partner /
analytic filters, draft entries, fold/unfold, drill-down to journal items and
the general ledger, and PDF / XLSX export:

* Statement Reports: **Balance Sheet**, **Profit and Loss**, **Cash Flow Statement**
* Audit Reports: **General Ledger**, **Trial Balance** (optional account-group
  hierarchy), **Journal Report**
* Partner Reports: **Partner Ledger**, **Aged Receivable**, **Aged Payable**
  (as of any date: later payments are ignored)
* Taxes & Fiscal: **Tax Report** (base and tax per tax, sales and purchases,
  cash-basis aware) with a *Closing Entry* button
* Management: **Custom Reports** / Configuration > Reporting > **Financial
  Reports**: renders ``account.report`` definitions, i.e. the localization tax
  reports and statements you design yourself (account codes, domains, tax tags,
  formulas on other lines, manual values). See the *Help* tab of a report.

The current year earnings and previous years' earnings are computed the way
Odoo does it: income and expense accounts restart at each fiscal year, their
past balance shows as unallocated earnings until it is allocated.

Bank and reconciliation
=======================

Accounting > Bank: bank transactions (statement lines), statements and
reconciliation models. *Reconcile* matches a transaction with open invoices,
bills and payments (full or partial), adds write-offs (bank fees...) by hand or
from a reconciliation model, keeps any remainder in the suspense account, and
can be undone. *Auto-Reconcile* (button and daily job) matches unambiguous
transactions by amount and partner or by reference, and applies the
*auto-reconcile* models. Journal items can also be reconciled together, with an
optional write-off.

Assets, deferrals, budgets, recurring entries
=============================================

Accounting > Management:

* **Assets**: fixed assets with linear / degressive / degressive-then-linear
  depreciation, monthly or yearly, prorata options, salvage value; posted
  automatically; pause, modify, impair, dispose or sell.
* **Deferred Revenues / Deferred Expenses**: the same engine recognising income
  or expense over time.
* Accounts can create assets automatically from bills/invoices
  (Configuration > Management > asset models, then the account's *Create Asset*).
* **Budgets**: planned vs. actual vs. theoretical per budgetary position and/or
  analytic account (*Budget Analysis* under Reporting > Management).
* **Recurring Entries**: journal entry templates generated on a schedule.

Customer follow-ups
===================

Customers > **Follow-up Reports**: overdue customers, reminder levels
(Configuration > Invoicing > Follow-up Levels: e.g. email at 15 days, letter at
30, call at 45), reminder emails and letters with the overdue invoices, activities,
customer statements, and an automatic daily run.

Fiscal years, lock dates and closing
====================================

* Configuration > Accounting > **Fiscal Years**: explicit fiscal years. Without
  records, Nepali companies (with ``l10n_np_ird``) automatically use the
  Shrawan–Asar year from the Bikram Sambat calendar (e.g. 2083/84 = 17 July
  2026 – 16 July 2027); other companies use the fiscal year end day and month of
  the settings. Every report, depreciation and closing tool goes through these
  dates.
* Accounting > Closing:

  * **Lock Dates**: global, tax, sales, purchase and (irreversible) hard lock
    dates; moving a date back can be a temporary *lock date exception* for you or
    everyone instead of a permanent change.
  * **Tax Return Closing**: moves the period's tax balances to the tax payable /
    receivable account (of the tax group, or the defaults set in Settings) and
    locks the period. A period cannot be closed twice.
  * **Year-End Earnings Allocation**: moves the unallocated profit or loss to a
    retained earnings account.
  * **Lock Date Exceptions**: history of the exceptions.

Recommended year end: reconcile the bank, post depreciation, close the last tax
period, allocate the earnings, then set the global and hard lock dates.

Not included
============

Services needing an external provider or a country outside Nepal: bank feeds
(online synchronization), OCR of bills, AvaTax, SEPA/ISO 20022 files,
Intrastat, consolidation, Silverfin. Bank statements are imported with the
standard *Import records* (CSV/XLSX) on the bank transactions list.

Tests
=====

::

    odoo-bin -d <db> -i ci_account --test-enable --test-tags /ci_account --stop-after-init
