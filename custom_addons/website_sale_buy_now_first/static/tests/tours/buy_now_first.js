import { registry } from '@web/core/registry';

const buttons = '#add_to_cart_wrap';

// The buttons still do the same in their new place
registry.category('web_tour.tours').add('website_sale_buy_now_first', {
    steps: () => [
        {
            content: 'Add to cart, below Buy now: stays on the page',
            trigger: `${buttons} > .o_we_buy_now.btn-primary + #add_to_cart.btn-outline-primary`,
            run: 'click',
        },
        {
            trigger: '.my_cart_quantity:contains(1)',
        },
        {
            content: 'Buy now: opens the cart',
            trigger: `${buttons} > .o_we_buy_now`,
            run: 'click',
            expectUnloadPage: true,
        },
        {
            content: 'The cart, with the product added twice',
            trigger: '#shop_cart .js_quantity[value="2"]',
        },
    ],
});
