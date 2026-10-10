import { registry } from '@web/core/registry';

const carousel = '#o-carousel-product';

// The shown slide (after its slide animation) and the active thumbnail
function shows(image, index) {
    return `${carousel}:has(li.active[data-bs-slide-to="${index}"]) .carousel-item.active:not(.carousel-item-start, .carousel-item-end) img.product_detail_img${image}`;
}

const phone = (index) => shows('[alt="Phone"]', index);
const media = (name, index) => shows(`[alt="${name}"]`, index);

// On a large screen, the previous / next arrows only show when hovering the images, which a tour can't do
function clickArrow(direction, content) {
    return {
        content,
        trigger: `${carousel} .carousel-outer`,
        run: (helpers) => helpers.click(`${carousel} .carousel-control-${direction}`),
    };
}

// Phone / Black: its image (the product's), then the Extra Product Media Front and Side
registry.category('web_tour.tours').add('website_sale_product_first_media_navigation', {
    steps: () => [
        {
            content: 'The page opens on the first media',
            trigger: media('Front', 1),
        },
        clickArrow('prev', 'Previous: the image of the variant'),
        {
            trigger: phone(0),
        },
        clickArrow('next', 'Next'),
        {
            trigger: media('Front', 1),
        },
        clickArrow('next', 'Next'),
        {
            trigger: media('Side', 2),
        },
        {
            content: 'Thumbnail of the image of the variant',
            trigger: `${carousel} li[data-bs-slide-to="0"]`,
            run: 'click',
        },
        {
            trigger: phone(0),
        },
        {
            content: 'Thumbnail of Side',
            trigger: `${carousel} li[data-bs-slide-to="2"]`,
            run: 'click',
        },
        {
            trigger: media('Side', 2),
        },
    ],
});

// Blue has its own image and the Extra Variant Media Blue back
registry.category('web_tour.tours').add('website_sale_product_first_media_variant', {
    steps: () => [
        {
            content: 'The page opens on the first media',
            trigger: media('Front', 1),
        },
        {
            content: 'Choose Blue',
            trigger: '.js_main_product label:has(> input.js_variant_change[data-value-name="Blue"])',
            run: 'click',
        },
        {
            content: 'The image of Blue',
            trigger: shows('[src*="(Blue)"]', 0),
        },
        clickArrow('next', 'Next: its first media'),
        {
            trigger: media('Blue back', 1),
        },
    ],
});
