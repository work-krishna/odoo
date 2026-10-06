import { registry } from '@web/core/registry';

function color(name) {
    return `.js_main_product label.css_attribute_color:has(> input[data-value-name="${name}"])`;
}

// Case: Black, Blue, and Red, archived
registry.category('web_tour.tours').add('website_sale_variant_picker_fix_single_attribute', {
    steps: () => [
        {
            content: 'Red is grayed out',
            trigger: `${color('Red')}.css_not_available`,
        },
        {
            trigger: `${color('Blue')}:not(.css_not_available)`,
        },
        {
            content: 'Blue',
            trigger: color('Blue'),
            run: 'click',
        },
        {
            trigger: `${color('Blue')}.active`,
        },
        {
            content: 'Red is still grayed out',
            trigger: `${color('Red')}.css_not_available`,
        },
    ],
});
