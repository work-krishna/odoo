import { patch } from '@web/core/utils/patch';
import { WebsiteSale } from '@website_sale/interactions/website_sale';

patch(WebsiteSale.prototype, {
    /**
     * Also gray out the variants that can't be chosen of a product with a single attribute: Odoo grays out the value
     * of such a variant "because of" the other values of the variant, of which there are none.
     *
     * @override method from `@website_sale/js/variant_mixin`
     */
    _checkExclusions(parent, combination) {
        super._checkExclusions(...arguments);
        const exclusionsEl = parent.querySelector('ul[data-attribute-exclusions]');
        const exclusions = JSON.parse(exclusionsEl?.dataset.attributeExclusions || '{}');
        for (const archivedCombination of exclusions.archived_combinations || []) {
            if (archivedCombination.length === 1) {
                this._disableInput(parent, archivedCombination[0]);
            }
        }
    },

    /**
     * Gray out the attribute value, and not another input of the product form: Odoo looks for any input with that
     * value, and the hidden product or product template id comes first when it's the same number as the attribute
     * value's id. Nothing when the value isn't on the page (hidden by another module).
     *
     * @override method from `@website_sale/js/variant_mixin`
     */
    _disableInput(parent, attributeValueId, ...args) {
        const attributes = parent.querySelector('ul.js_add_cart_variants[data-attribute-exclusions]') || parent;
        if (!attributes.querySelector(`option[value="${attributeValueId}"], input[value="${attributeValueId}"]`)) {
            return;
        }
        return super._disableInput(attributes, attributeValueId, ...args);
    },
});
