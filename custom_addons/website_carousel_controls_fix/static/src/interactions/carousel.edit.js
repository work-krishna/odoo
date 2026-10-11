import { patch } from '@web/core/utils/patch';
import { CarouselEdit } from '@website/interactions/carousel.edit';

const ARROWS = [
    ['.carousel-control-prev', 'prev'],
    ['.carousel-control-next', 'next'],
];

patch(CarouselEdit.prototype, {
    /**
     * When the editing ends, gives the previous / next arrows back what makes them slide the carousel, as Odoo does
     * for the indicators. Odoo gives them back what they had when the editing started, which is nothing for a carousel
     * already saved without it, so that it would be saved without it again: its arrows would only work in the editor.
     *
     * @override
     */
    destroy() {
        super.destroy();
        if (this.services.website_edit.isEditingTranslations()) {
            return;
        }
        for (const [selector, direction] of ARROWS) {
            for (const arrowEl of this.el.querySelectorAll(selector)) {
                arrowEl.setAttribute('data-bs-slide', direction);
            }
        }
    },
});
