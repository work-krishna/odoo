import { expect, test } from "@odoo/hoot";
import { waitFor } from "@odoo/hoot-dom";
import { contains } from "@web/../tests/web_test_helpers";
import {
    defineWebsiteModels,
    setupWebsiteBuilder,
} from "@website/../tests/builder/website_helpers";

defineWebsiteModels();

// 12 × 5 px
const image =
    "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAwAAAAFCAIAAAD+GJp4AAAAFElEQVR4nGM8YWPDQAgwEVRBf0UA6aIBSmn+2uEAAAAASUVORK5CYII=";

const carouselHtml = `
    <section class="s_carousel_wrapper p-0" data-snippet="s_carousel" data-name="Carousel" data-vcss="001">
        <div id="rcTest" class="s_carousel s_carousel_default carousel slide" data-bs-ride="false" data-bs-interval="10000">
            <div class="carousel-inner">
                <div class="carousel-item active" data-name="Slide">
                    <div class="container">
                        <div class="row"><div class="col-12"><img src="${image}" alt=""/></div></div>
                    </div>
                </div>
            </div>
        </div>
    </section>`;

async function select(label, item) {
    await contains(`.hb-row[data-label='${label}'] button`).click();
    await contains(`.o-hb-select-dropdown-item:contains('${item}')`).click();
}

async function setupBannerOptions() {
    const { getEditableContent } = await setupWebsiteBuilder(carouselHtml);
    await contains(":iframe .carousel").click();
    await contains(".hb-row[data-label='Banner options'] input").click();
    return getEditableContent().querySelector(".carousel");
}

test("banner options are shown once turned on", async () => {
    const { getEditableContent } = await setupWebsiteBuilder(carouselHtml);
    const carouselEl = getEditableContent().querySelector(".carousel");
    await contains(":iframe .carousel").click();
    expect(".hb-row[data-label='Banner options']").toHaveCount(1);
    expect(".hb-row[data-label='Banner height']").toHaveCount(0);

    await contains(".hb-row[data-label='Banner options'] input").click();
    expect(carouselEl).toHaveClass("o_rich_carousel");
    expect(".hb-row[data-label='Banner height']").toHaveCount(1);
    expect(".hb-row[data-label='Image fit']").toHaveCount(1);
    expect(".hb-row[data-label='Desktop']").toHaveCount(0);
});

test("fixed height, per screen size", async () => {
    const carouselEl = await setupBannerOptions();

    await select("Banner height", "Fixed");
    expect(carouselEl).toHaveClass("o_rc_height_fixed");
    // Starts from the current height
    expect(carouselEl.style.getPropertyValue("--o-rc-height")).toMatch(/^\d+px$/);

    await contains(".hb-row[data-label='Desktop'] input").edit("320");
    expect(carouselEl.style.getPropertyValue("--o-rc-height")).toBe("320px");
    expect(".hb-row[data-label='Tablet'] input").toHaveValue("");
    await contains(".hb-row[data-label='Mobile'] input").edit("180");
    expect(carouselEl.style.getPropertyValue("--o-rc-height-mobile")).toBe("180px");
    // Emptied: back to the bigger screens' height
    await contains(".hb-row[data-label='Mobile'] input").clear();
    expect(carouselEl.style.getPropertyValue("--o-rc-height-mobile")).toBe("");

    await select("Banner height", "Auto");
    expect(carouselEl).not.toHaveClass("o_rc_height_fixed");
    expect(".hb-row[data-label='Desktop']").toHaveCount(0);
});

test("ratio, matching the image", async () => {
    const carouselEl = await setupBannerOptions();

    await select("Banner height", "Ratio");
    expect(carouselEl).toHaveClass("o_rc_height_ratio");
    await select("Ratio", "12:5");
    expect(carouselEl).toHaveClass("o_rc_ratio_12x5");
    await select("Mobile ratio", "4:5");
    expect(carouselEl).toHaveClass("o_rc_mobile_ratio_4x5");

    await select("Ratio", "Match image");
    // Once the image is loaded
    await waitFor(":iframe .carousel.o_rc_ratio_image");
    expect(carouselEl).not.toHaveClass("o_rc_ratio_12x5");
    expect(carouselEl).toHaveClass("o_rc_ratio_image");
    expect(carouselEl.style.getPropertyValue("--o-rc-ratio")).toBe("12 / 5");

    await select("Ratio", "16:9");
    expect(carouselEl).not.toHaveClass("o_rc_ratio_image");
    expect(carouselEl.style.getPropertyValue("--o-rc-ratio")).toBe("");
});

test("image, arrows and sliding options", async () => {
    const carouselEl = await setupBannerOptions();

    await select("Image fit", "Stretch");
    expect(carouselEl).toHaveClass("o_rc_fit_stretch");
    // Nothing to keep in view in a stretched image
    expect(".hb-row[data-label='Image focus']").toHaveCount(0);
    await select("Image fit", "Contain");
    expect(carouselEl).toHaveClass("o_rc_fit_contain");
    expect(carouselEl).not.toHaveClass("o_rc_fit_stretch");
    await select("Image focus", "Top");
    expect(carouselEl).toHaveClass("o_rc_focus_top");

    await contains(".hb-row[data-label='Edge to edge'] input").click();
    expect(carouselEl).toHaveClass("o_rc_edge_to_edge");
    await select("Arrow size", "Large");
    expect(carouselEl).toHaveClass("o_rc_arrows_large");
    await contains(".hb-row[data-label='Arrows on hover'] input").click();
    expect(carouselEl).toHaveClass("o_rc_arrows_hover");

    expect(".hb-row[data-label='Pause on hover'] input").toBeChecked();
    await contains(".hb-row[data-label='Pause on hover'] input").click();
    expect(carouselEl).toHaveAttribute("data-bs-pause", "false");
    await contains(".hb-row[data-label='Loop'] input").click();
    expect(carouselEl).toHaveAttribute("data-bs-wrap", "false");
    await contains(".hb-row[data-label='Swipe'] input").click();
    expect(carouselEl).toHaveAttribute("data-bs-touch", "false");
    await contains(".hb-row[data-label='Swipe'] input").click();
    expect(carouselEl).not.toHaveAttribute("data-bs-touch");
});

test("turning the banner options off removes them all", async () => {
    const carouselEl = await setupBannerOptions();
    await select("Banner height", "Fixed");
    await contains(".hb-row[data-label='Desktop'] input").edit("320");
    await select("Image fit", "Stretch");
    await contains(".hb-row[data-label='Loop'] input").click();

    await contains(".hb-row[data-label='Banner options'] input").click();
    expect(carouselEl).toHaveClass("s_carousel carousel slide");
    expect([...carouselEl.classList].filter((name) => /^o_rc_|^o_rich_/.test(name))).toEqual([]);
    expect(carouselEl.style.getPropertyValue("--o-rc-height")).toBe("");
    expect(carouselEl).not.toHaveAttribute("data-bs-wrap");
    expect(".hb-row[data-label='Banner height']").toHaveCount(0);
});
