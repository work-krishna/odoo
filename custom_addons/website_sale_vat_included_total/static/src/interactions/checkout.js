import { patch } from '@web/core/utils/patch';
import { Checkout } from '@website_sale/interactions/checkout';

patch(Checkout.prototype, {
    /**
     * Replace the summary's Order Detail table with the one rendered for the new delivery method,
     * which can change its rows, its amounts and whether the total includes tax.
     *
     * @override method from `@website_sale/interactions/checkout`
     */
    _updateCartSummary(result, targetEl) {
        super._updateCartSummary(...arguments);
        const orderDetail = targetEl.querySelector('table[name="o_order_detail"]');
        if (orderDetail && result.order_detail) {
            orderDetail.outerHTML = result.order_detail;
        }
    },
});
