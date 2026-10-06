import { registry } from '@web/core/registry';

const product = '.js_main_product';

// A color's label, a storage's pill
function value(name) {
    return `${product} :is(label, li.o_variant_pills):has(> input.js_variant_change[data-value-name="${name}"])`;
}

// Publish Phone: the Red variants and Blue / 256 GB are hidden
registry.category('web_tour.tours').add('website_sale_variant_publish', {
    steps: () => [
        {
            content: 'No Red',
            trigger: `${product}:has(input[data-value-name="Blue"]):not(:has(input[data-value-name="Red"]))`,
        },
        {
            trigger: `${value('256 GB')}:not(.css_not_available)`,
        },
        {
            content: 'Blue',
            trigger: value('Blue'),
            run: 'click',
        },
        {
            content: 'Blue / 256 GB is hidden',
            trigger: `${value('256 GB')}.css_not_available`,
        },
        {
            trigger: `${product} #add_to_cart:not(.disabled)`,
        },
        {
            content: '256 GB anyway',
            trigger: value('256 GB'),
            run: 'click',
        },
        {
            content: 'Cannot be added to the cart',
            trigger: `${product}.css_not_available #add_to_cart.disabled`,
        },
    ],
});

// The list of the variants
registry.category('web_tour.tours').add('website_sale_variant_publish_list', {
    steps: () => [
        {
            content: 'Search the phone',
            trigger: '.o_searchview_input',
            run: 'edit Publish Phone',
        },
        {
            trigger: '.o_searchview_autocomplete .o-dropdown-item:first',
            run: 'click',
        },
        {
            content: 'Its 6 variants',
            trigger: '.o_searchview_facet:contains(Publish Phone)',
        },
        {
            trigger: '.o_control_panel .o_pager_value:contains(1-6)',
        },
        {
            content: 'Hide Red / 128 GB',
            trigger: `
                .o_data_row:has(.o_tag:contains(Red)):has(.o_tag:contains(128 GB))
                td[name="is_variant_published"] input:checked
            `,
            run: 'click',
        },
        {
            trigger: `
                .o_data_row:has(.o_tag:contains(Red)):has(.o_tag:contains(128 GB))
                td[name="is_variant_published"] input:not(:checked)
            `,
        },
        {
            content: 'Saved without opening the variant',
            trigger: '.o_list_view:not(:has(.o_data_row.o_selected_row)):not(:has(.o_list_record_save))',
        },
        {
            trigger: `
                .o_data_row:has(.o_tag:contains(Blue)):has(.o_tag:contains(128 GB))
                td[name="is_variant_published"] input:checked
            `,
        },
    ],
});
