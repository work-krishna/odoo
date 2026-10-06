import { registry } from '@web/core/registry';

const filters = '#products_grid_before form.js_attributes';
const grid = '.o_wsale_products_grid_table_wrapper';

function clickFilter(name) {
    return {
        content: `Check/uncheck ${name}`,
        trigger: `${filters} .form-check:contains(${name}) input`,
        run: 'click',
        expectUnloadPage: true,
    };
}

// Starts on the shop's page of a category with the test products only
registry.category('web_tour.tours').add('website_sale_product_brand_filter', {
    steps: () => [
        {
            content: 'The brands come first, above the attributes',
            trigger: `${filters} .o_wsale_brand_filter:first-child ~ .accordion-item:contains(Storage)`,
        },
        clickFilter('Apple'),
        {
            content: 'Only Apple products',
            trigger: `${grid}:contains(iPhone 17 Pro):not(:contains(Galaxy S25)):not(:contains(Chicken Momo))`,
        },
        clickFilter('Samsung'),
        {
            trigger: `${grid}:contains(iPhone 17 Pro):contains(Galaxy S25):not(:contains(Chicken Momo))`,
        },
        clickFilter('512 GB'),
        {
            content: 'The brands are kept with an attribute',
            trigger: `${filters} .form-check:contains(Samsung) input:checked`,
        },
        {
            trigger: `${grid}:contains(Galaxy S25):not(:contains(iPhone 17 Pro)):not(:contains(Chicken Momo))`,
        },
        {
            content: 'Clear the filters, brands included',
            trigger: '#products_grid_before a[title="Clear Filters"]',
            run: 'click',
            expectUnloadPage: true,
        },
        {
            trigger: `${grid}:contains(Chicken Momo):contains(Galaxy S25):contains(iPhone 17 Pro)`,
        },
        {
            content: 'Open the iPhone',
            trigger: `${grid} a:contains(iPhone 17 Pro)`,
            run: 'click',
            expectUnloadPage: true,
        },
        {
            content: 'Follow its brand',
            trigger: '.o_wsale_product_brand:contains(Brand:) a:contains(Apple)',
            run: 'click',
            expectUnloadPage: true,
        },
        {
            content: 'The shop shows the Apple products',
            trigger: `${filters} .form-check:contains(Apple) input:checked`,
        },
        {
            trigger: `${grid}:contains(iPhone 17 Pro):not(:contains(Galaxy S25)):not(:contains(Chicken Momo))`,
        },
    ],
});
