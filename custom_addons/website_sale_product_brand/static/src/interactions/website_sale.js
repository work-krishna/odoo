import { patch } from '@web/core/utils/patch';
import { WebsiteSale } from '@website_sale/interactions/website_sale';
import wSaleUtils from '@website_sale/js/website_sale_utils';

patch(WebsiteSale.prototype, {
    /**
     * Filter the shop on the checked brands too: the shop URL is built from the filters form's
     * action, which gets the checked brands, in place of the ones the page was filtered on.
     *
     * @override method from `@website_sale/interactions/website_sale`
     */
    onChangeAttribute(ev) {
        const form = wSaleUtils.getClosestProductForm(ev.currentTarget);
        const action = new URL(form.action);
        const brands = [...form.querySelectorAll('input[name="brand"]:checked')].map(input => input.value);
        if (brands.length) {
            action.searchParams.set('brand', brands.join(','));
        } else {
            action.searchParams.delete('brand');
        }
        form.action = action.toString();
        super.onChangeAttribute(...arguments);
    },
});
