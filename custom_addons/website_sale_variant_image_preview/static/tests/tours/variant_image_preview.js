import { registry } from '@web/core/registry';

const product = '.js_main_product';

// The item of an attribute value in its list
function value(name) {
    return `${product} .o_wsale_product_attribute > li:has(input.js_variant_change[data-value-name="${name}"])`;
}

// A color's label, a storage's pill
function choice(name) {
    return `${product} :is(label, li.o_variant_pills):has(> input.js_variant_change[data-value-name="${name}"])`;
}

// The displayed image is the one of the variant: its URL ends with the variant's name, "Phone (Blue, 256 GB)"
function shows(color, storage) {
    return `#o-carousel-product .carousel-item.active img.product_detail_img[src*="(${color},%20${storage}%20GB)"]`;
}

// Black / 128 GB, Blue / 128 GB and Blue / 256 GB have their own image, the other variants don't
registry.category('web_tour.tours').add('website_sale_variant_image_preview', {
    steps: () => [
        {
            content: 'Black / 128 GB',
            trigger: shows('Black', 128),
        },
        {
            content: 'Hover Blue',
            trigger: value('Blue'),
            run: 'hover',
        },
        {
            content: 'Blue / 128 GB is shown',
            trigger: shows('Blue', 128),
        },
        {
            content: 'Hover Red, which has no image',
            trigger: value('Red'),
            run: 'hover',
        },
        {
            content: 'Black / 128 GB is shown back',
            trigger: shows('Black', 128),
        },
        {
            content: 'Hover 256 GB: Black / 256 GB has no image',
            trigger: value('256 GB'),
            run: 'hover',
        },
        {
            trigger: shows('Black', 128),
        },
        {
            content: 'Choose Blue',
            trigger: choice('Blue'),
            run: 'click',
        },
        {
            trigger: `${choice('Blue')}.active`,
        },
        {
            trigger: shows('Blue', 128),
        },
        {
            content: 'Hover 256 GB',
            trigger: value('256 GB'),
            run: 'hover',
        },
        {
            content: 'Blue / 256 GB is shown',
            trigger: shows('Blue', 256),
        },
        {
            content: 'Leave',
            trigger: `${product} h1`,
            run: 'hover',
        },
        {
            trigger: shows('Blue', 128),
        },
        {
            content: 'Choose 256 GB',
            trigger: choice('256 GB'),
            run: 'click',
        },
        {
            trigger: `${choice('256 GB')}.active`,
        },
        {
            trigger: shows('Blue', 256),
        },
        {
            content: 'Hover Black: Black / 256 GB has no image',
            trigger: value('Black'),
            run: 'hover',
        },
        {
            trigger: shows('Blue', 256),
        },
    ],
});

// On mobile: no preview, the images of the chosen variant
registry.category('web_tour.tours').add('website_sale_variant_image_preview_mobile', {
    steps: () => [
        {
            trigger: shows('Black', 128),
        },
        {
            content: 'Hover Blue',
            trigger: value('Blue'),
            run: 'hover',
        },
        {
            content: 'No preview',
            trigger: shows('Black', 128),
        },
        {
            content: 'Choose Blue',
            trigger: choice('Blue'),
            run: 'click',
        },
        {
            trigger: shows('Blue', 128),
        },
    ],
});
