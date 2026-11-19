# Nepal Can Move: eCommerce

Adds Nepal Can Move to the shop's checkout:

- **District and delivery area** fields under the address, for Nepal addresses (checkout and *My addresses*). The area tells Odoo which NCM branch delivers there.
- **Collect at an NCM branch**: the customer picks a branch in the pickup dialog, searching by town, district or area, and the delivery price is updated to that branch.

It installs itself when both the shop and `delivery_ncm` are installed. Setup, daily use and troubleshooting are in [`delivery_ncm/README.md`](../delivery_ncm/README.md).
