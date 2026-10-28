import { patch } from '@web/core/utils/patch';
import { WebsiteSale } from '@website_sale/interactions/website_sale';

patch(WebsiteSale.prototype, {
    /**
     * Show Add to Cart back, without "Out of Stock", on choosing a variant whose inventory isn't tracked after one
     * marked out of stock: Odoo leaves the product page as it is for such a variant.
     *
     * @override method from `@website_sale_stock/js/variant_mixin`
     */
    _onChangeCombinationStock(ev, parent, combination) {
        if (!combination.is_storable && parent.matches('.js_main_product')) {
            const ctaWrapper = parent.querySelector('#o_wsale_cta_wrapper');
            ctaWrapper?.classList.replace('d-none', 'd-flex');
            ctaWrapper?.classList.remove('out_of_stock');
            this.el.querySelectorAll('.availability_message_' + combination.product_template)
                .forEach(el => el.remove());
        }
        return super._onChangeCombinationStock(...arguments);
    },
});
