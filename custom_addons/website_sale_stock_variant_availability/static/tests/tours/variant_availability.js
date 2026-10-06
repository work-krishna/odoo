import { registry } from '@web/core/registry';

const product = '.js_main_product';

// The label of a color, the pill of a storage: their radio button is hidden
function value(name) {
    return `${product} :is(label, li):has(> input.js_variant_change[data-value-name="${name}"])`;
}

function selected(name) {
    return `${product} :is(label, li).active:has(> input[data-value-name="${name}"]:checked)`;
}

function grayedOut(name) {
    return `${product} :is(label, li):has(> input[data-value-name="${name}"]).css_not_available`;
}

function available(name) {
    return `${product} :is(label, li):has(> input[data-value-name="${name}"]):not(.css_not_available)`;
}

// Phone: Black / 128 GB and Red / * are out of stock, Black / 256 GB, Blue / 128 GB and Blue / 256 GB are not
registry.category('web_tour.tours').add('website_sale_stock_variant_availability', {
    steps: () => [
        {
            content: 'Opens on the first variant in stock',
            trigger: selected('Black'),
        },
        {
            trigger: selected('256 GB'),
        },
        {
            content: 'Red / 256 GB is out of stock',
            trigger: grayedOut('Red'),
        },
        {
            content: 'Black / 128 GB is out of stock',
            trigger: grayedOut('128 GB'),
        },
        {
            trigger: available('Blue'),
        },
        {
            trigger: `${product} #add_to_cart:not(.disabled)`,
        },
        {
            content: 'Blue',
            trigger: value('Blue'),
            run: 'click',
        },
        {
            content: 'Blue / 128 GB is in stock',
            trigger: available('128 GB'),
        },
        {
            trigger: grayedOut('Red'),
        },
        {
            trigger: available('Black'),
        },
        {
            content: 'Red, out of stock anyway',
            trigger: value('Red'),
            run: 'click',
        },
        {
            content: 'Cannot be added to the cart',
            trigger: `${product} #o_wsale_cta_wrapper.out_of_stock:not(:visible)`,
        },
        {
            trigger: `${product} #out_of_stock_message:contains(Out of Stock)`,
        },
        {
            trigger: grayedOut('256 GB'),
        },
        {
            content: 'Back to Blue / 256 GB',
            trigger: value('Blue'),
            run: 'click',
        },
        {
            trigger: `${product} #o_wsale_cta_wrapper:not(.out_of_stock) #add_to_cart:not(.disabled)`,
        },
    ],
});
