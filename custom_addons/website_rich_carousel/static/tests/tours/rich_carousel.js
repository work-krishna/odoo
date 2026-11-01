import { registry } from "@web/core/registry";

function check(condition, message) {
    if (!condition) {
        throw new Error(message);
    }
}

function near(value, expected, message) {
    check(Math.abs(value - expected) <= 1, `${message}: ${value} instead of ${expected}`);
}

function slide(carouselId) {
    return document.querySelector(`#${carouselId} .carousel-item.active`);
}

function imageRect(carouselId) {
    return slide(carouselId).querySelector("img").getBoundingClientRect();
}

// The image fills the slide, whose height is the one asked for.
function checkFilledSlide(carouselId, height) {
    const slideEl = slide(carouselId);
    near(slideEl.offsetHeight, height, `Height of #${carouselId}`);
    const imageEl = slideEl.querySelector("img");
    near(imageRect(carouselId).height, height, `Image height of #${carouselId}`);
    near(
        imageRect(carouselId).width,
        imageEl.parentElement.getBoundingClientRect().width,
        `Image width of #${carouselId}`
    );
}

// Once the carousels are started
const ready = "#rc_contain .carousel-item.active[style*='min-height']";

registry.category("web_tour.tours").add("website_rich_carousel_desktop", {
    steps: () => [
        {
            content: "Fixed height",
            trigger: ready,
            run() {
                checkFilledSlide("rc_fixed", 300);
            },
        },
        {
            content: "Ratio 12:5, edge to edge",
            trigger: ready,
            run() {
                const slideEl = slide("rc_ratio");
                checkFilledSlide("rc_ratio", (slideEl.offsetWidth * 5) / 12);
                near(
                    imageRect("rc_ratio").width,
                    document.querySelector("#rc_ratio").getBoundingClientRect().width,
                    "The image should be as wide as the carousel"
                );
            },
        },
        {
            content: "Stretched background image",
            trigger: ready,
            run() {
                const slideEl = slide("rc_background");
                near(slideEl.offsetHeight, 250, "Height of #rc_background");
                const backgroundSize = getComputedStyle(slideEl).backgroundSize;
                check(backgroundSize === "100% 100%", `Background size: ${backgroundSize}`);
            },
        },
        {
            content: "Contain, focus, rounded corners, transition and sliding",
            trigger: ready,
            run() {
                const imageStyle = getComputedStyle(slide("rc_contain").querySelector("img"));
                check(imageStyle.objectFit === "contain", `Image fit: ${imageStyle.objectFit}`);
                check(
                    imageStyle.objectPosition === "50% 0%",
                    `Image focus: ${imageStyle.objectPosition}`
                );
                const transition = getComputedStyle(slide("rc_contain")).transitionDuration;
                check(transition === "1.2s", `Transition time: ${transition}`);
                const innerEl = document.querySelector("#rc_contain .carousel-inner");
                const radius = getComputedStyle(innerEl).borderTopLeftRadius;
                check(radius === "16px", `Rounded corners: ${radius}`);
                const config = window.Carousel.getInstance(
                    document.querySelector("#rc_contain")
                )._config;
                check(config.pause === false, "The carousel shouldn't pause on hover");
                check(config.wrap === false, "The carousel shouldn't loop");
                check(config.touch === false, "The carousel shouldn't swipe");
            },
        },
        {
            content: "No banner options: nothing changes",
            trigger: ready,
            run() {
                check(slide("rc_plain").offsetHeight !== 123, "The height shouldn't be fixed");
                const fit = getComputedStyle(slide("rc_plain").querySelector("img")).objectFit;
                check(fit === "cover", `Image fit: ${fit}`);
            },
        },
    ],
});

registry.category("web_tour.tours").add("website_rich_carousel_mobile", {
    steps: () => [
        {
            content: "Mobile height",
            trigger: ready,
            run() {
                checkFilledSlide("rc_fixed", 180);
            },
        },
        {
            content: "Mobile ratio 1:1",
            trigger: ready,
            run() {
                checkFilledSlide("rc_ratio", slide("rc_ratio").offsetWidth);
            },
        },
        {
            content: "No mobile height: the desktop one",
            trigger: ready,
            run() {
                near(slide("rc_background").offsetHeight, 250, "Height of #rc_background");
            },
        },
    ],
});
