import { registry } from '@web/core/registry';

const filmstrip = '#o_wsale_categories_filmstrip';
const prev = '.o_wsale_filmstrip_arrow_prev';
const next = '.o_wsale_filmstrip_arrow_next';

// The 15 categories of the test don't fit at the top of the shop
registry.category('web_tour.tours').add('website_sale_categories_arrows', {
    steps: () => [
        {
            content: 'At the start: only the right arrow',
            trigger: `${filmstrip}.o_wsale_filmstrip_scrollable:has(${prev}:disabled) ${next}:not(:disabled)`,
            run: 'click',
        },
        {
            content: 'Scrolled: both arrows',
            trigger: `${filmstrip}:has(${next}:not(:disabled)) ${prev}:not(:disabled)`,
            run() {
                const wrapperEl = document.querySelector(`${filmstrip} .o_wsale_filmstrip_wrapper`);
                if (wrapperEl.scrollLeft <= 0) {
                    throw new Error('The categories should have been scrolled');
                }
                wrapperEl.scrollLeft = wrapperEl.scrollWidth;
            },
        },
        {
            content: 'At the end: only the left arrow',
            trigger: `${filmstrip}:has(${next}:disabled) ${prev}:not(:disabled)`,
            run: 'click',
        },
        {
            content: 'Scrolled back: both arrows',
            trigger: `${filmstrip}:has(${prev}:not(:disabled)) ${next}:not(:disabled)`,
            run() {
                // Only a few categories left: they fit
                for (const categoryEl of document.querySelectorAll(`${filmstrip} .o_wsale_filmstrip > li:nth-child(n+3)`)) {
                    categoryEl.remove();
                }
            },
        },
        {
            content: 'The categories fit: no arrows',
            trigger: `${filmstrip}:not(.o_wsale_filmstrip_scrollable):has(${prev}:not(:visible)):has(${next}:not(:visible)) .o_wsale_filmstrip_link`,
        },
    ],
});
