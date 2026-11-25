# NCM API Integration Questions

Nov 19, 2026 · @Krishna

We (Chaitanya Innovation Pvt. Ltd, NCM vendor ID 59083) are connecting our Odoo 19 online shop to the NCM API (documentation version 2026-05-28) and need these 31 questions answered before we go live. Sections A–H block the launch; section I (COD settlement) can follow before the first remittance.

We tested the demo and production branch and rate endpoints with read-only requests only; no orders were created. Please write answers in the NCM answer column, or reply by question number.

## A. Vendor accounts

| # | Question | NCM answer |
| --- | --- | --- |
| 1 | **Two companies.** Our vendor account (ID 59083) is registered to Chaitanya Innovation Pvt. Ltd. We also run a second company. If both ship through NCM, should each have its own vendor account and token, with its own pickup branch and COD settlement? |  |

## B. Branches and coverage

| # | Question | NCM answer |
| --- | --- | --- |
| 2 | **Branch identifiers.** Order creation takes branch names (`fbranch`, `branch`), while redirect takes a branch ID (`destination`). Should we send `name` exactly as `/api/v2/branches` returns it (e.g. TINKUNE), and `pk` for redirect? Can a branch be renamed, and is name matching case-sensitive? |  |
| 3 | **Branch vs Logistics points.** The production list has 249 "Branch" and 400 "Logistics" entries. Can customers collect parcels at Logistics points (Door2Branch, Branch2Branch), or only at Branch type? Can a Logistics point be the destination for home delivery? |  |
| 4 | **Areas covered.** We plan to let customers pick their area from `areas_covered` and use that area's branch as the destination. Is this the intended use? 475 area names (e.g. BAGBAZAR, TUDIKHEL, KHALANGA) appear under more than one branch: how should we choose? If an area is in no list, do you still deliver there, and to which branch should we send it? |  |
| 5 | **Branch data.** How often does the branch list change, and how often should we sync it? 338 branches have no geocode; can you add coordinates, since customers will choose collection branches on a map? |  |

## C. Rates and charges

| # | Question | NCM answer |
| --- | --- | --- |
| 6 | **Weight.** `/api/v1/shipping-rate` takes no weight, but order creation accepts `weight` (default 1 kg). How does weight change the delivery charge (per-kg slabs)? Can the rate endpoint take a weight? |  |
| 7 | **Branch surcharge.** Is the branch `surcharge` already included in the `/shipping-rate` result? On demo, TINKUNE to POKHARA (surcharge 0) quoted NPR 170, and TINKUNE to JANAKPUR (surcharge 280) quoted NPR 270. |  |
| 8 | **Delivery type values.** Please confirm the mapping between the rate `type` and the order `delivery_type`: Pickup/Collect = Door2Door, Send = Branch2Door, D2B = Door2Branch, B2B = Branch2Branch. Does `/shipping-rate` need a token in production? It answers without one on demo. |  |
| 9 | **Other charges.** Besides the delivery charge, what can be charged per order: COD handling fee, VAT on delivery charges, return, redirect (REDIRECT, RDRT-DiFF-BRNCH), exchange, fragile or valuable handling? Please share the current rate card. |  |

## D. Creating orders

| # | Question | NCM answer |
| --- | --- | --- |
| 10 | **COD amount.** For orders already paid online, is `cod_charge` "0" accepted? Are decimals accepted (e.g. "1499.50")? Is there a maximum COD amount per order? |  |
| 11 | **COD includes delivery.** Please confirm with this example: a phone at NPR 25,000 plus NPR 150 delivery means we send `cod_charge` 25150, the customer pays NPR 25,150, and you remit NPR 25,150 minus your charges. |  |
| 12 | **Phone format.** Which formats do `phone` and `phone2` accept: 10-digit mobile numbers only, landlines, a +977 prefix? |  |
| 13 | **Field limits.** What are the maximum lengths of `name`, `address`, `package`, `instruction` and `vref_id`? Must `vref_id` be unique, and is it shown on the label and searchable in the portal? |  |
| 14 | **Duplicate orders.** If our create request times out, how can we tell whether the order was created? Can we look up an order by `vref_id`, or will you reject a repeated `vref_id`? We want to avoid duplicates, as your documentation asks. |  |
| 15 | **High-value parcels.** We ship mobile phones worth NPR 20,000 to 200,000. Is there an API field for declared value or insurance, and for handling (Fragile, Valuable)? The label data returns `handling`, but order creation has no such field. Can one order contain several packets? |  |
| 16 | **Pickups.** For Door2Door orders created by API, is pickup scheduled automatically, or must we raise a Pickup ticket each day? What is the cut-off time for same-day pickup? |  |

## E. Cancellations, changes and returns

| # | Question | NCM answer |
| --- | --- | --- |
| 17 | **Cancelling.** The API has no cancel endpoint. How do we cancel an order created by mistake before pickup, and is there a charge? |  |
| 18 | **Changes before pickup.** Can the COD amount, phone, address or weight be changed before pickup? Is `/api/v2/vendor/order/redirect` the only way, and does it charge a redirect fee before pickup? |  |
| 19 | **Returns.** In which statuses can we call `/api/v2/vendor/order/return`? What does a return cost, and which statuses does the order pass through until it reaches us? |  |
| 20 | **Exchanges.** For `/api/v2/vendor/order/exchange-create`, what COD amount and delivery charge do the two new orders get? Can we set the COD on the new customer order? |  |

## F. Statuses and tracking

| # | Question | NCM answer |
| --- | --- | --- |
| 21 | **Full status list.** Please send every order status value (exact strings), what each means, and which are final. We have seen: Pickup Order Created, Drop off Order Created, Sent for Pickup, Pickup Complete, Arrived, In Transit, Sent for Delivery, Delivered, Sent to Vendor. |  |
| 22 | **Payment status.** What values can `payment_status` take in the order details, and what does each mean? Does "Completed" mean the COD was collected from the customer, or remitted to us? |  |
| 23 | **Customer tracking page.** Is there a public page where customers can track an order? What is its URL format, so we can link it in our order emails? |  |

## G. Webhooks

| # | Question | NCM answer |
| --- | --- | --- |
| 24 | **Payloads.** The documentation shows only the test payload. Please share real examples of the order delivery and order comment webhook events. Do they include the NCM order ID as a number, our `vref_id` and the comment text? Which `event` values exist? |  |
| 25 | **Delivery and retries.** What response do you expect (any 2xx)? How long do you wait (10 seconds, as in the test)? How often do you retry a failed call, and can an event arrive twice or out of order? |  |
| 26 | **Scope.** Does the webhook fire for every order on our account, including orders created in the portal or by bulk upload? |  |

## H. Labels and errors

| # | Question | NCM answer |
| --- | --- | --- |
| 27 | **Labels.** Must labels follow a specific size or barcode (e.g. Code 128 of the NCM order ID) so your branches can scan them? We plan to print our own 100 × 150 mm label from the label API data. |  |
| 28 | **Error responses.** Some errors come back as HTML instead of JSON. On demo, an unknown branch name on `/api/v1/shipping-rate` returns status 500 with a full Django debug page. Can errors return JSON with a 4xx status? That debug page also exposes server configuration, which you may want to turn off. |  |

## I. COD settlement and accounting

These can follow go-live, but we need them before your first COD remittance to us.

| # | Question | NCM answer |
| --- | --- | --- |
| 29 | **Settlement cycle.** How often do you remit COD, and is it by bank transfer only? Must we raise a COD transfer ticket each time, or is settlement automatic? |  |
| 30 | **Settlement statement.** Do you provide a statement for each remittance, listing every order's COD collected, delivery charge, other charges and net amount? Is it available by API, or as a file (which format)? |  |
| 31 | **Charges and VAT.** Are your charges deducted from the COD remittance or invoiced separately? Do you issue a VAT invoice for them, and how are charges on prepaid (COD 0) orders billed? |  |
