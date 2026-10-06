import { registry } from '@web/core/registry';

const product = '.js_main_product';
const price = `${product} .oe_price .oe_currency_value`;
const caseRow = `
    .o_sale_product_configurator_table_optional
    tr:has(div[name="o_sale_product_configurator_name"] span:contains(Case))
`;

// Phone: 12GB/256GB costs 50 more, Glossy 3 more. Its optional product, Case: Leather 5, Glossy 3, Lanyard 2 more
registry.category('web_tour.tours').add('website_sale_hide_variant_extra_price', {
    steps: () => [
        {
            content: 'No extra price next to the attribute values',
            trigger: `${product}:has(label:contains(12GB/256GB)):not(:has(.variant_price_extra))`,
        },
        {
            trigger: `${price}:contains(100.00)`,
        },
        {
            content: 'Choose 12GB/256GB',
            trigger: `${product} label:has(input[data-value-name="12GB/256GB"])`,
            run: 'click',
        },
        {
            content: 'Its price',
            trigger: `${price}:contains(150.00)`,
        },
        {
            trigger: `${product} select:has(option:contains(Glossy))`,
            run: 'selectByLabel Glossy',
        },
        {
            trigger: `${price}:contains(153.00)`,
        },
        {
            content: 'Add to cart: the optional products',
            trigger: '#add_to_cart',
            run: 'click',
        },
        {
            content: 'No extra price next to the attribute values of the case',
            trigger: `${caseRow}:has(span:contains(Leather)):has(label:contains(Lanyard)):not(:has(.badge))`,
        },
        {
            trigger: `${caseRow} select:has(option:contains(Glossy)):not(:has(option:contains("+")))`,
        },
        {
            trigger: `${caseRow} td.o_sale_product_configurator_price span:contains(10.00)`,
        },
        {
            content: 'Leather',
            trigger: `${caseRow} span:contains(Leather)`,
            run: 'click',
        },
        {
            trigger: `${caseRow} select`,
            run: 'selectByLabel Glossy',
        },
        {
            content: 'The extra prices still apply',
            trigger: `${caseRow} td.o_sale_product_configurator_price span:contains(18.00)`,
        },
    ],
});
