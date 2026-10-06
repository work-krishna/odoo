import { patch } from '@web/core/utils/patch';
import { WebsiteSale } from '@website_sale/interactions/website_sale';

patch(WebsiteSale.prototype, {
    /**
     * Gray out the attribute value, and not another input of the product form: Odoo looks for any input with that
     * value, and the hidden product or product template id comes first when it's the same number as the attribute
     * value's id.
     *
     * @override method from `@website_sale/js/variant_mixin`
     */
    _disableInput(parent, ...args) {
        const attributes = parent.querySelector('ul.js_add_cart_variants[data-attribute-exclusions]');
        return super._disableInput(attributes || parent, ...args);
    },
});
