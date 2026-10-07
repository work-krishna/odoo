import { registry } from '@web/core/registry';

const grid = '#o_wsale_products_grid';
const showMore = '#o_wsale_pager .o_wsale_show_more';

// The grid has exactly `count` products, all different
function products(count) {
    return {
        content: `${count} products`,
        trigger: `${grid}:has(> .oe_product:nth-child(${count})):not(:has(> .oe_product:nth-child(${count + 1})))`,
        run() {
            const ids = [...this.anchor.children].map((el) => el.dataset.productTemplateId);
            if (new Set(ids).size !== count) {
                throw new Error(`The same product is shown twice: ${ids}`);
            }
        },
    };
}

function isPlaceSaved() {
    const state = history.state?.wsaleShowMore;
    const product = state && document.querySelector(`${grid} > [data-product-template-id="${state.productId}"]`);
    return product && Math.abs(product.getBoundingClientRect().top - state.top) < 1;
}

// 10 products, 4 per page. Not the browser's back button: Chrome restores the page from its cache, as it was
// (the tour can't go on), and otherwise the products come back as when refreshing the page.
registry.category('web_tour.tours').add('website_sale_shop_show_more', {
    steps: () => [
        products(4),
        {
            content: 'No page numbers',
            trigger: `#o_wsale_pager:not(:has(.pagination))`,
        },
        {
            content: 'Show more',
            trigger: `${showMore}:not(.d-none)`,
            run: 'click',
        },
        products(8),
        {
            content: 'Show more, again',
            trigger: `${showMore}:not(.d-none)`,
            run: 'click',
        },
        products(10),
        {
            content: 'No more products',
            trigger: `#o_wsale_pager:has(.o_wsale_show_more.d-none)`,
        },
        {
            content: 'Add to the cart a product that was added',
            trigger: `${grid} > .oe_product:nth-child(10)`,
            run: `hover && click ${grid} > .oe_product:nth-child(10) .o_wsale_product_btn_primary`,
        },
        {
            content: 'In the cart',
            trigger: 'a sup.my_cart_quantity:text(1)',
        },
        {
            content: 'Scroll down to the last product, and refresh the page',
            trigger: `${grid} > .oe_product:nth-child(10)`,
            async run() {
                this.anchor.scrollIntoView({ block: 'center', behavior: 'instant' });
                // Until the place on the page is saved
                while (!isPlaceSaved()) {
                    await new Promise((resolve) => setTimeout(resolve, 50));
                }
                window.location.reload();
            },
            expectUnloadPage: true,
        },
        products(10),
        {
            content: 'Still no more products',
            trigger: `#o_wsale_pager:has(.o_wsale_show_more.d-none)`,
        },
        {
            content: 'Back at the last product',
            trigger: `${grid} > .oe_product:nth-child(10)`,
            async run() {
                // The page is scrolled while the products out of the screen take their place
                const isInView = () => {
                    const { top, bottom } = this.anchor.getBoundingClientRect();
                    return bottom > 0 && top < window.innerHeight;
                };
                for (let wait = 0; wait < 20 && !isInView(); wait++) {
                    await new Promise((resolve) => setTimeout(resolve, 50));
                }
                if (!isInView()) {
                    throw new Error(`The last product is out of view: ${this.anchor.getBoundingClientRect().top}px from the top`);
                }
            },
        },
    ],
});
