import { clickOnSave, registerWebsitePreviewTour } from '@website/js/tours/tour_utils';

const carousel = ':iframe #myCarouselTest';

// The page's carousel was saved without the direction of its arrows (data-bs-slide)
registerWebsitePreviewTour(
    'website_carousel_controls_fix_save',
    {
        url: '/carousel-test',
        edition: true,
    },
    () => [
        {
            content: 'Select the carousel',
            trigger: `${carousel} .carousel-item.active .container`,
            run: 'click',
        },
        {
            content: 'Change it: invert its colors',
            trigger: ".o_customize_tab [data-container-title='Carousel'] [data-label='Invert colors'] input",
            run: 'click',
        },
        {
            trigger: `${carousel}.carousel-dark`,
        },
        ...clickOnSave(),
        {
            content: 'Saved with the direction of its arrows',
            trigger: `${carousel}.carousel-dark:has(.carousel-control-prev[data-bs-slide="prev"]) .carousel-control-next[data-bs-slide="next"]`,
        },
    ]
);
