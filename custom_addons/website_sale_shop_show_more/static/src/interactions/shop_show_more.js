import { Interaction } from '@web/public/interaction';
import { registry } from '@web/core/registry';
import { redirect } from '@web/core/utils/urls';

// The pages added to the shop, kept in the browser's history entry of the shop
const HISTORY_KEY = 'wsaleShowMore';

async function fetchPage(url) {
    const response = await fetch(url);
    if (!response.ok) {
        throw new Error(`${url}: ${response.status}`);
    }
    return new DOMParser().parseFromString(await response.text(), 'text/html');
}

export class ShopShowMore extends Interaction {
    static selector = '#o_wsale_pager:has(.o_wsale_show_more)';

    dynamicContent = {
        '.o_wsale_show_more': {
            't-on-click.prevent': this.locked(this.onClickShowMore, true),
            't-att-href': () => this.nextUrl,
            't-att-class': () => ({ 'd-none': !this.nextUrl }),
        },
        // Saved while scrolling: Chrome ignores the changes made to the history entry when leaving the page
        _window: { 't-on-scroll.noUpdate': this.debounced(this.saveState, 200) },
    };

    setup() {
        this.grid = document.querySelector('#o_wsale_products_grid');
        this.nextUrl = this.el.querySelector('.o_wsale_show_more').getAttribute('href');
        this.addedUrls = [];
        this.addedProducts = [];
        this.registerCleanup(() => this.addedProducts.forEach((el) => el.remove()));
    }

    start() {
        // Back to the shop (back button, refresh): the products that were added come back
        const state = history.state?.[HISTORY_KEY];
        if (state?.urls?.length) {
            this.restore(state);
        }
    }

    async onClickShowMore() {
        const url = this.nextUrl;
        try {
            await this.addPages([url]);
        } catch {
            redirect(url);
            return;
        }
        this.saveState();
    }

    async restore({ urls, productId, top }) {
        const nextUrl = this.nextUrl;
        this.nextUrl = '';
        this.updateContent();
        try {
            await this.addPages(urls);
        } catch {
            this.nextUrl = nextUrl;
            return;
        }
        // Back to the product that was at the top of the screen. Not to the same scroll position: the products out of
        // the screen take less space until they are shown (`content-visibility: auto`), the page is shorter now, and
        // grows as they are shown.
        const product = this.grid.querySelector(`:scope > [data-product-template-id="${productId}"]`);
        for (let frame = 0; product && frame < 20; frame++) {
            const distance = product.getBoundingClientRect().top - top;
            if (Math.abs(distance) < 1) {
                break;
            }
            window.scrollBy({ top: distance, behavior: 'instant' });
            await this.waitFor(new Promise((resolve) => requestAnimationFrame(resolve)));
        }
    }

    /**
     * Add the products of the pages to the grid, and point the button to the page after them.
     *
     * @param {string[]} urls
     */
    async addPages(urls) {
        const pages = await this.waitFor(Promise.all(urls.map(fetchPage)));
        this.protectSyncAfterAsync(() => {
            const shown = new Set([...this.grid.children].map((el) => el.dataset.productTemplateId));
            const products = pages.flatMap((page) => [
                ...page.querySelectorAll('#o_wsale_products_grid > [data-product-template-id]'),
            ]).filter((el) => {
                const isNew = !shown.has(el.dataset.productTemplateId);
                shown.add(el.dataset.productTemplateId);
                return isNew;
            });
            const interactions = this.services['public.interactions'];
            interactions.stopInteractions(this.grid);
            this.grid.append(...products);
            this.addedProducts.push(...products);
            // The interactions around the grid (add to cart, compare, ...) listen to the elements that were there
            // when they started: make them listen to the new products too
            for (const colibri of interactions.interactions) {
                if (colibri.el?.contains(this.grid) && colibri.hasStarted && !colibri.isDestroyed && !colibri.isUpdating) {
                    colibri.updateContent();
                }
            }
            // Restarted on the whole grid, as some handle all its products at once (variants preview, ...)
            interactions.startInteractions(this.grid);
            this.nextUrl = pages.at(-1).querySelector('#o_wsale_pager .o_wsale_show_more')?.getAttribute('href') || '';
            this.addedUrls.push(...urls);
        })();
    }

    saveState() {
        if (!this.addedUrls.length) {
            return;
        }
        // The first product on the screen, and where
        const product = [...this.grid.children].find((el) => el.getBoundingClientRect().bottom > 0);
        history.replaceState({
            ...history.state,
            [HISTORY_KEY]: {
                urls: this.addedUrls,
                productId: product?.dataset.productTemplateId,
                top: product?.getBoundingClientRect().top,
            },
        }, '');
    }
}

registry.category('public.interactions').add('website_sale_shop_show_more.shop_show_more', ShopShowMore);
