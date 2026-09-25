{
    'name': 'Nepal - IRD Compliance (BS calendar, fiscal-year numbering, CBMS)',
    'version': '19.0.1.1.0',
    'countries': ['np'],
    'category': 'Accounting/Localizations',
    'summary': 'Bikram Sambat dates, Shrawan-Asar fiscal-year invoice numbering and IRD CBMS invoice sync',
    'description': """
Nepal - IRD Compliance
======================
Builds on l10n_np (chart of accounts, VAT, TDS) with what IRD requires of
billing software:

* Bikram Sambat (BS) calendar: invoice date and fiscal year in BS on the
  invoice form, list and printed invoice (BS 1975-2100)
* Customer invoices and credit notes numbered per Nepali fiscal year
  (Shrawan 1 to the end of Asar), e.g. INV/2083-84/0001, up to FY 2099/00;
  sales receipts and entries of the same journal get series of their own
  (INV/RCPT/2083-84/0001, INV/MISC/2083-84/0001)
* IRD CBMS (Central Billing Monitoring System) sync: every posted customer
  invoice and credit note is queued and sent to /api/bill or /api/billreturn
  with the VAT-taxable, exempt and export buckets; failures are retried by a
  cron and shown on the invoice. Invoices IRD holds, or may hold after a
  send with an unknown outcome, cannot be reset, cancelled or renamed.

Not included: IRD e-billing software certification items beyond these
(e.g. printed-copy counters, materialized sales register views).
""",
    'author': 'Krishna Kumar Sah',
    'license': 'LGPL-3',
    'depends': ['l10n_np'],
    'data': [
        'data/ir_cron.xml',
        'views/res_company_views.xml',
        'views/account_move_views.xml',
        'report/report_invoice.xml',
    ],
    'post_init_hook': '_l10n_np_ird_post_init',
    'installable': True,
}
