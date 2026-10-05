import { patch } from '@web/core/utils/patch';
import { Checkout } from '@website_sale/interactions/checkout';

patch(Checkout.prototype, {
    /**
     * Show "Incl. VAT" under the total only while it includes tax: the new delivery method's line
     * can bring tax into the total or take it out.
     *
     * @override method from `@website_sale/interactions/checkout`
     */
    _updateCartSummary(result, targetEl) {
        super._updateCartSummary(...arguments);
        targetEl.querySelector('[name="o_order_total_tax_note"]')?.classList.toggle(
            'd-none', !result.total_includes_tax
        );
    },
});
