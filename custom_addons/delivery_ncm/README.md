# Nepal Can Move shipping for Odoo 19

Ship with [Nepal Can Move](https://www.nepalcanmove.com) (NCM) from Odoo: NCM quotes the delivery price, validating a delivery order creates the NCM order with the cash to collect, and NCM's status updates and comments come back to the delivery order.

Two modules work together:

| Module | What it adds |
| --- | --- |
| `delivery_ncm` | The two NCM delivery methods, NCM branches and areas, sending parcels, labels, status and comment syncing, customer emails, tracking on the customer's order page |
| `website_sale_ncm` | The district and area picker in the shop's address form; collect-at-branch price updates at checkout. Installs itself when the shop (`website_sale`) and `delivery_ncm` are both installed |

Contents: [Before you start](#before-you-start) · [Setting up](#setting-up) · [Daily use](#daily-use) · [Troubleshooting](#troubleshooting) · [For developers](#for-developers)

## Before you start

- **An NCM vendor account.** Its API page in the NCM vendor portal shows the production token, the demo token and the two webhook fields. Only the company that owns this account should ship with NCM.
- **Inventory and a warehouse** for that company: NCM orders are created from delivery orders.
- **Phone numbers on customers.** NCM refuses an order without a valid Nepali phone number. NCM also identifies customers by phone: if it already knows the number, its label shows the name it has on file, not the one Odoo sent.
- **Product weights**, if heavier parcels cost more (see *Extra Charge per kg* below).
- **wkhtmltopdf on the server**, for PDF labels. Without it the delivery is still sent; the chatter says the label could not be generated.
- **Postal codes.** Odoo requires a ZIP code for Nepal addresses by default. If your customers don't know theirs, untick *Zip Required* in Contacts → Configuration → Countries → Nepal.

Install the modules like any other (`-i delivery_ncm,website_sale_ncm`). A deployment that only pulls code and restarts does not install or upgrade them.

## Setting up

Open **Inventory → Configuration → Delivery Methods**. Installing the module created two methods: **Home delivery (Nepal Can Move)** (NCM collects from you and delivers to the door) and **Collect at an NCM branch** (the customer picks the parcel up at a branch they choose). Set up the first one, then repeat steps 2–4 on the second.

1. **Company**: set the company that owns the NCM account.
2. **Token**: on the *Nepal Can Move* tab, paste the token. The method starts in *Test Environment*, which talks to NCM's demo server: use the demo token printed on the portal's API page. The demo server knows only a few branches (Tinkune to Pokhara works).
3. **Pickup branches**: click **Check account**. It lists the branches NCM assigned to your account; choose one of them as *Default Pickup Branch*. A product that leaves from another branch gets that branch in its own *NCM Pickup Branch* (product form → Inventory tab → Logistics). A warehouse can have one too, used for its products that have none. The order of precedence is product, then warehouse, then this default. *Check account* also flags product and warehouse branches NCM did not assign to you.
4. **Branches**: click **Update NCM branches** once. The list of about 650 branches and 5,800 delivery areas is then refreshed every night.
5. **Webhook** (production server only, it needs a public HTTPS address): click **Register webhook**. NCM's API only sets the delivery webhook, so copy the *Webhook URL* into the portal's *Order Comment Webhook URL* field too, then click **Test webhook**. Status updates also arrive every 30 minutes without the webhook, so it only makes them faster.
6. **Go live**: click the *Test Environment* button to switch to *Production*, and paste the production token from the portal.
7. **Prices**: NCM's quote is used as is. *Margin on Rate*, *Additional margin* and *Free if order amount is above* work as for any delivery method. NCM's price API ignores weight, so *Extra Charge per kg* adds that amount for each kg above 1 kg until NCM confirms its weight charges.
8. **Customer emails** (optional): tick *Email Customers* to email the customer when the parcel goes out for delivery and when it is delivered.
9. **Website**: publish both methods (the *Published* toggle on each). Both allow cash on delivery: enable the *Cash on Delivery* payment provider in Website → Configuration → Payment Providers if you want to offer it. The shop hides an NCM method while it cannot ship the cart: no token, or a product without any pickup branch.
10. **Delivery operation type**: keep *Generate Shipping Labels* ticked on Inventory → Configuration → Operation Types → Delivery Orders. That is what makes validating a delivery send it to NCM.

The *Nepal Can Move* tab repeats these steps for whoever opens the method later.

## Daily use

### Taking orders

- **On the website**, a customer with a Nepal address sees *District* and *Delivery area* under the address. The area tells Odoo which NCM branch delivers there. At checkout they choose home delivery, or collect at a branch: a dialog lists the branches of their district, and they can search by town, district or area. The delivery price is updated once they choose a branch.
- **In a quotation**, use *Add shipping* and pick an NCM method. Odoo needs to know the customer's branch: set *NCM Delivery Area* on the customer's contact (under the address), or make sure the city is a town NCM serves. Otherwise the quote says *Choose the NCM delivery area of the shipping address*.

### Sending a parcel

Validate the delivery order as usual. Odoo creates the NCM order, and the delivery order shows:

- **Tracking Reference**: the NCM order number.
- **NCM Pickup Branch**, **NCM Destination Branch**, **Cash to Collect** and **Delivery Instruction**: what was sent to NCM. Check them *before* validating: they can't be changed afterwards. *Cash to Collect* is what the customer owes for this parcel: its items, taxes included, plus its delivery charge. It is 0 when they paid online. Set it to 0 yourself for orders paid another way (bank transfer, cash at the counter).
- **A label** in the chatter (100 × 150 mm). Print it again with the **NCM Label** button.
- **Shipping Cost**: NCM's actual charge for the order.

**One parcel per pickup branch.** When an order mixes products from different pickup branches, confirming it creates one delivery order per branch, and each becomes its own NCM order with its own label. At checkout the customer paid the total of NCM's quotes. Each parcel collects for its own items plus its own quote, so the parcels' cash adds up to the order total. If a parcel goes out in two parts (a backorder), the first part carries the delivery charge.

If NCM refuses the order, the message gives NCM's reason (for example *phone: Invalid Phone Number*). Fix it and validate again.

If NCM does not answer in time, the order may or may not exist at NCM, so Odoo will not send it again on its own. A yellow banner appears on the delivery order. Look for the order reference (the sales order number) in the NCM portal:

- found it: type its number in *NCM Order* and click **Use this NCM order**;
- not there: click **Create NCM order anyway**.

### Following a parcel

- The **NCM Stage** badge and the **Nepal Can Move** tab show the status, its history and NCM's comments. Comments from NCM staff also appear as notes in the chatter.
- Updates come by webhook, and every 30 minutes (statuses) and 15 minutes (comments) anyway. **Refresh NCM** fetches them now.
- **Message NCM** posts a comment on the NCM order (NCM accepts one per order per minute).
- The customer sees the stage, the branch to collect from and the cash to pay on their order page in the portal.

### Cancelling

NCM's API cannot cancel an order. Click **Cancel** next to the tracking reference: Odoo posts a cancellation request on the NCM order and gives you a to-do to cancel it in the NCM portal or by phone. Sending the delivery again afterwards creates a new NCM order.

Returns, exchanges, redirects, pickup requests and COD transfer requests are not in Odoo yet: use the NCM portal.

### Where things are

- Inventory → Configuration → Delivery → **NCM Branches** and **NCM Delivery Areas**.
- In developer mode, the same menu also has **NCM Order Attempts** (every order creation, kept even when the validation failed) and **NCM Webhook Calls**.
- Settings → Technical → Scheduled Actions: the four *NCM: …* jobs.

## Troubleshooting

| You see | Why | What to do |
| --- | --- | --- |
| *Choose the NCM delivery area of the shipping address…* | Odoo can't tell which branch delivers to that address (many area names exist in several places) | Set the customer's *NCM Delivery Area*, or the *NCM Destination Branch* on the delivery order |
| *No NCM pickup branch for (a product)…* | Neither the product, its warehouse nor the delivery method has a pickup branch | Set the product's *NCM Pickup Branch*, or a *Default Pickup Branch* on the method |
| An NCM method doesn't show at checkout | The shop hides it when it can't ship the cart: no token, or a product without a pickup branch | Fix as in the row above, and check the token |
| Red banner: *This transfer mixes products from several NCM pickup branches* | The transfer was made or edited by hand with products of different branches | Move each branch's products to their own transfer |
| *Nepal Can Move refused the order…: phone: Invalid Phone Number* | NCM wants a 10-digit Nepali number | Fix the customer's phone; `+977` and spaces are removed automatically |
| *NCM returned an unexpected response (HTTP 500). … Branch matching query does not exist* | That NCM server doesn't know the branch, which is usual on the demo server | On demo, use branches it knows (Tinkune, Pokhara…). In production, click *Update NCM branches* |
| The delivery has no label, and a note says the label could not be generated | wkhtmltopdf is missing on the server | Install wkhtmltopdf, then use **NCM Label** |
| *NCM did not accept the token* | Wrong token, or the demo token on a *Production* method (or the other way round) | Check the token against the environment button |
| Statuses stop changing | Webhook not registered, or the scheduled jobs are off | **Test webhook**; check the *NCM: …* scheduled actions; look at *NCM Webhook Calls* |
| NCM's label shows another customer name | NCM keeps the first name it saw for a phone number | Ask NCM to correct the customer, or note it in the delivery instruction |
| Collect-at-branch shows no branches | The customer's district has no NCM branch, or the search matched nothing | Search a nearby town in the dialog |

## For developers

### How a parcel flows

1. **Quote.** `delivery.carrier._ncm_rate_groups()` groups the order's goods by pickup branch (`_ncm_pickup_branch_for()`: product → warehouse → method default). `sale.order._ncm_get_dest_branch()` gives the destination (chosen pickup branch → contact's area → guess from the address). Then each branch's parcel is quoted with `/api/v1/shipping-rate`, cached for 24 hours per route. `ncm_rate_shipment()` returns the total, and `set_delivery_line()` stores the per-branch quotes in `sale.order.ncm_rate_breakdown`.
2. **Split.** `stock.move._key_assign_picking()` and `_search_picking_for_assignation_domain()` include the move's pickup branch, so confirming an order creates one transfer per branch (`stock.picking.ncm_from_branch_id`). Each transfer's `ncm_cod_amount` is its items (taxes included) plus its share of the delivery charge, weighted by `ncm_rate_breakdown`, times the unpaid part of the order.
3. **Send.** Validating calls `stock_delivery`'s `send_to_shipper()` → `ncm_send_shipping()` → `_ncm_send_picking()`, which builds the payload in `stock.picking._ncm_prepare_order_values()` and calls `/api/v1/order/create`.
4. **Track.** The webhook (`/delivery_ncm/webhook/<secret>`) only queues an `ncm.webhook.event`; a job re-reads the order from NCM's API, so the payload is never trusted. Jobs also poll `/api/v1/orders/statuses` in batches of 100 and `/api/v1/order/getbulkcomments`.

### Duplicate protection

NCM has no idempotency key and no lookup by our reference, and it warns against duplicate orders. Every creation attempt is written to `ncm.api.log` **through a separate cursor**, so the row survives when the validation is rolled back. Before creating an order, `_ncm_send_picking()` looks for attempts newer than the delivery's `ncm_log_checkpoint`: it reuses one NCM *created*, and refuses to retry one whose outcome is *uncertain* (read timeout, dropped connection). Never update `ncm.api.log` rows from the main transaction: under PostgreSQL's REPEATABLE READ they are invisible to it, and an update raises a serialization error. Only insert them, and move the checkpoint.

### NCM API behaviour not in its documentation

- Production is `https://portal.nepalcanmove.com`, with the same paths as the demo server. `/api/v2/branches` and `/api/v1/shipping-rate` answer without a token.
- Errors can be HTML or plain-text Django debug pages with HTTP 500. `NcmClient` shows only their first lines.
- An order with no comments returns HTTP 200 `{"detail": "No comments found"}`, not a list.
- `/api/v1/order` also returns `trackid`, `destination_branch_name`, `destination_branch_phone`, `delivered_date` and `vendor_return`.
- Branches are matched by exact name when creating orders, but redirects take the branch id.
- Throttling: 3 requests per second, 1 comment per order per minute; daily quotas are shown on the portal's API page.
- Branch coordinates have more than 7 decimals: round them before comparing, or every sync rewrites them.

### Running the tests

```
odoo-bin --addons-path=addons,odoo/addons,custom_addons -d <test db> \
    -i delivery_ncm,website_sale_ncm --test-tags /delivery_ncm,/website_sale_ncm --stop-after-init
```

The tests never reach NCM: `tests/common.py` routes `NcmClient._http` to `FakeNcm`, whose canned answers are shaped like NCM's real ones. Odoo 19 notes:

- `TransactionCase` does not put the registry in test mode, so `NcmCommon` does it; otherwise the separate cursor commits for real.
- Odoo's `assertRaises` rolls back like a failed request; `assertRaisesRegex` does not.
- Calling `button_validate()` from a script first returns the SMS confirmation wizard when `stock_sms` is installed: use `with_context(skip_sms=True)`.

### Waiting for NCM's answers

| Open question | Where it lands |
| --- | --- |
| Full list of status strings | `const.STATUS_MAP` (unknown ones fall back to keywords in `status_to_state`) |
| How weight changes the charge | Replace `ncm_extra_kg_price` with NCM's rule |
| Whether customers can collect at 'Logistics' points | The `branch_type` filter in `_ncm_get_close_locations` |
| How to cancel an order | `ncm_cancel_shipment` (today a comment and a to-do) |
| Real webhook payloads and signing | `extract_order_id` in `models/delivery_carrier.py`, and the controller |
| Public tracking page | The carrier's *Tracking Link* (`<shipmenttrackingnumber>`); `ncm_track_id` holds NCM's `trackid` |

### Next phases

- **Operations**: return (`/api/v2/vendor/order/return`), exchange (`…/exchange-create`), redirect (`…/redirect`), pickup and COD-transfer tickets (`/api/v2/vendor/ticket/…`), and a COD risk check with `/api/v2/vendor/ratings?phone=` (block or flag cash on delivery for customers who often refuse parcels). Add them as buttons or wizards on the delivery order, next to *Message NCM*.
- **COD accounting**: a clearing journal for the cash NCM holds, NCM's charges as vendor bills, and matching NCM's payouts. It depends on how NCM settles: `ncm_payment_status` and `ncm_delivery_charge` are already stored on each delivery.
