import { patch } from '@web/core/utils/patch';
import { Checkout } from '@website_sale/interactions/checkout';

/**
 * NCM re-prices the order once the customer chooses a collection branch (the charge depends on
 * the branch): refresh the delivery price badge and the order totals.
 */
patch(Checkout.prototype, {
    async _onPickupLocationConfirmed() {
        await super._onPickupLocationConfirmed(...arguments);
        const radio = document.querySelector('input[name="o_delivery_radio"]:checked');
        if (radio?.dataset.deliveryType !== 'ncm') {
            return;
        }
        const result = await this.waitFor(this._setDeliveryMethod(radio.dataset.dmId));
        this._updateAmountBadge(radio, result);
        this._updateCartSummaries(result);
    },
});
