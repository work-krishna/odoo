import { Interaction } from '@web/public/interaction';
import { registry } from '@web/core/registry';

/**
 * On the product page, hovering an attribute value shows the image of the variant it leads to (the selected values,
 * with the hovered one instead) in place of the displayed image, if this variant has its own image. Leaving the value
 * shows the image back; choosing it keeps the image, until it's replaced with the images of the chosen variant.
 *
 * The images are given with the page (`data-variant-image-previews`): hovering doesn't ask the server anything.
 */
export class VariantImagePreview extends Interaction {
    static selector = '.js_main_product ul.js_add_cart_variants[data-variant-image-previews]';
    dynamicContent = {
        '.o_wsale_product_attribute > li': {
            't-on-mouseenter': this.onMouseEnterValue,
            't-on-mouseleave': this.onMouseLeaveValue,
        },
        'input.js_variant_change': { 't-on-change': this.onChangeValue },
    };

    setup() {
        this.imageUrls = JSON.parse(this.el.dataset.variantImagePreviews);
        this.previewedImage = null;
        this.originalSrc = null;
    }

    destroy() {
        this.restoreImage();
    }

    /**
     * @param {MouseEvent} ev
     */
    onMouseEnterValue(ev) {
        const input = ev.currentTarget.querySelector('input.js_variant_change:not(.no_variant)');
        // Not on mobile, as Odoo's variant preview in the shop
        if (this.env.isSmall || !input || input.checked) {
            return;
        }
        const imageUrl = this.imageUrls[this.getCombinationKey(input)];
        const image = imageUrl && this.getDisplayedImage();
        if (!image) {
            return;
        }
        if (!this.previewedImage) {
            this.previewedImage = image;
            this.originalSrc = image.getAttribute('src');
        }
        image.setAttribute('src', imageUrl);
    }

    onMouseLeaveValue() {
        this.restoreImage();
    }

    onChangeValue() {
        // Chosen: the preview stays, as the image of the chosen variant
        this.previewedImage = null;
    }

    restoreImage() {
        if (this.previewedImage) {
            this.previewedImage.setAttribute('src', this.originalSrc);
            this.previewedImage = null;
        }
    }

    /**
     * The combination of the variant the given attribute value leads to: the selected values, with this one instead
     * of the selected value of its attribute. As the `combination_indices` of the variant: the sorted ids of its
     * attribute values (`product.template.attribute.value`), without those of the attributes not creating variants.
     *
     * @param {HTMLInputElement} input the attribute value
     * @returns {string}
     */
    getCombinationKey(input) {
        const selected = this.el.querySelectorAll(
            'input.js_variant_change:not(.no_variant):checked, select.js_variant_change:not(.no_variant)'
        );
        const ids = [...selected].filter((el) => el.name !== input.name).map((el) => parseInt(el.value));
        ids.push(parseInt(input.value));
        return ids.sort((a, b) => a - b).join(',');
    }

    /**
     * The main image of the product page: the current one of the carousel, or the first one of the grid.
     *
     * @returns {HTMLImageElement|null}
     */
    getDisplayedImage() {
        return this.el.closest('.oe_website_sale')?.querySelector(
            '#o-carousel-product .carousel-item.active img.product_detail_img, #o-grid-product img.product_detail_img'
        );
    }
}

registry
    .category('public.interactions')
    .add('website_sale_variant_image_preview.variant_image_preview', VariantImagePreview);
