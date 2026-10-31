import { registry } from '@web/core/registry';
import { Interaction } from '@web/public/interaction';

export class CategoriesArrows extends Interaction {
    static selector = '#o_wsale_categories_filmstrip';
    dynamicContent = {
        _root: {
            't-att-class': () => ({ o_wsale_filmstrip_scrollable: this.isScrollable }),
        },
        '.o_wsale_filmstrip_wrapper': {
            't-on-scroll': this.throttled(this.update),
        },
        '.o_wsale_filmstrip_arrow_prev': {
            't-on-click': () => this.scroll(-1),
            't-att-disabled': () => this.atStart,
        },
        '.o_wsale_filmstrip_arrow_next': {
            't-on-click': () => this.scroll(1),
            't-att-disabled': () => this.atEnd,
        },
    };

    setup() {
        this.wrapperEl = this.el.querySelector('.o_wsale_filmstrip_wrapper');
        this.arrowEls = [...this.el.querySelectorAll('.o_wsale_filmstrip_arrow')];
        this.isScrollable = false;
        this.update();
        // The categories overflow or not when the page is resized, or their images are loaded
        const resizeObserver = new ResizeObserver(this.throttled(this.update));
        resizeObserver.observe(this.el);
        resizeObserver.observe(this.wrapperEl.firstElementChild);
        this.registerCleanup(() => resizeObserver.disconnect());
    }

    update() {
        const overflow = this.wrapperEl.scrollWidth - this.wrapperEl.clientWidth;
        // The categories get back the place of the arrows when they're hidden
        const arrowsWidth = this.isScrollable ? this.arrowEls.reduce((width, el) => width + el.offsetWidth, 0) : 0;
        this.isScrollable = overflow - arrowsWidth > 1;
        // Right to left, scrollLeft goes from 0 down to -overflow
        const scrolled = Math.abs(this.wrapperEl.scrollLeft);
        this.atStart = scrolled <= 1;
        this.atEnd = scrolled >= overflow - 1;
    }

    /**
     * Scrolls the categories by most of what is shown, so that the last one shown stays in sight
     *
     * @param {number} direction -1 towards the start, 1 towards the end
     */
    scroll(direction) {
        const isRtl = getComputedStyle(this.wrapperEl).direction === 'rtl';
        this.wrapperEl.scrollBy({
            left: direction * (isRtl ? -1 : 1) * this.wrapperEl.clientWidth * 0.8,
            behavior: 'smooth',
        });
    }
}

registry.category('public.interactions').add('website_sale_categories_arrows.categories_arrows', CategoriesArrows);
