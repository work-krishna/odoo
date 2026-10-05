import { registry } from '@web/core/registry';
import * as tourUtils from '@website_sale/js/tours/tour_utils';

const taxNote = 'div.o_total_card [name="o_order_total_tax_note"]';

function selectDeliveryMethod(name) {
    return {
        content: `Select ${name}`,
        trigger: `#o_delivery_methods [name="o_delivery_method"]:contains(${name}) input[name="o_delivery_radio"]`,
        run: 'click',
    };
}

registry.category('web_tour.tours').add('website_sale_vat_included_total_delivery', {
    url: '/shop',
    steps: () => [
        ...tourUtils.addToCart({ productName: 'Untaxed Charger', expectUnloadPage: true }),
        tourUtils.goToCart(),
        tourUtils.goToCheckout(),
        selectDeliveryMethod('Courier with VAT'),
        {
            content: 'The total includes the VAT of the delivery',
            trigger: `${taxNote}:visible:contains(Incl. VAT)`,
        },
        {
            trigger: 'div.o_total_card tr[name="o_order_total"] .oe_currency_value:text(213.00)',
        },
        selectDeliveryMethod('Free Pickup'),
        {
            content: 'The total no longer includes any tax',
            trigger: `${taxNote}:not(:visible)`,
        },
        {
            trigger: 'div.o_total_card tr[name="o_order_total"] .oe_currency_value:text(100.00)',
        },
        selectDeliveryMethod('Courier with VAT'),
        {
            trigger: `${taxNote}:visible`,
        },
    ],
});
