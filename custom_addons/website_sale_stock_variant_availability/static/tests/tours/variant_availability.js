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

// Marked Phone, whose inventory isn't tracked: Red / 128 GB is marked out of stock
registry.category('web_tour.tours').add('website_sale_stock_variant_marked_out_of_stock', {
    steps: () => [
        {
            trigger: selected('Black'),
        },
        {
            content: 'Red / 128 GB is out of stock',
            trigger: grayedOut('Red'),
        },
        {
            trigger: `${product} #add_to_cart:not(.disabled)`,
        },
        {
            content: 'Red anyway',
            trigger: value('Red'),
            run: 'click',
        },
        {
            content: 'Out of Stock, cannot be added to the cart',
            trigger: `${product} #out_of_stock_message:contains(Out of Stock)`,
        },
        {
            trigger: `${product} #o_wsale_cta_wrapper.out_of_stock:not(:visible)`,
        },
        {
            content: '256 GB',
            trigger: value('256 GB'),
            run: 'click',
        },
        {
            content: 'Red / 256 GB can be bought',
            trigger: `${product} #o_wsale_cta_wrapper:not(.out_of_stock) #add_to_cart:not(.disabled)`,
        },
        {
            trigger: `${product}:not(:has(#out_of_stock_message))`,
        },
    ],
});

// The list of the variants
registry.category('web_tour.tours').add('website_sale_stock_variant_marked_out_of_stock_list', {
    steps: () => [
        {
            content: 'Search the phone',
            trigger: '.o_searchview_input',
            run: 'edit Marked Phone',
        },
        {
            trigger: '.o_searchview_autocomplete .o-dropdown-item:first',
            run: 'click',
        },
        {
            trigger: '.o_searchview_facet:contains(Marked Phone)',
        },
        {
            trigger: '.o_control_panel .o_pager_value:contains(1-6)',
        },
        {
            content: 'Mark Red / 128 GB out of stock',
            trigger: `
                .o_data_row:has(.o_tag:contains(Red)):has(.o_tag:contains(128 GB))
                td[name="is_variant_out_of_stock"] input:not(:checked)
            `,
            run: 'click',
        },
        {
            trigger: `
                .o_data_row:has(.o_tag:contains(Red)):has(.o_tag:contains(128 GB))
                td[name="is_variant_out_of_stock"] input:checked
            `,
        },
        {
            content: 'Saved without opening the variant',
            trigger: '.o_list_view:not(:has(.o_data_row.o_selected_row))',
        },
    ],
});
