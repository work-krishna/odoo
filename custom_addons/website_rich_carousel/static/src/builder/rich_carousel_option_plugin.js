import { BuilderAction } from "@html_builder/core/builder_action";
import { after, SNIPPET_SPECIFIC } from "@html_builder/utils/option_sequence";
import { Plugin } from "@html_editor/plugin";
import { withSequence } from "@html_editor/utils/resource";
import { registry } from "@web/core/registry";
import { RichCarouselOption } from "./rich_carousel_option";

// Right after the carousel's own options.
const RICH_CAROUSEL = after(SNIPPET_SPECIFIC);

class RichCarouselOptionPlugin extends Plugin {
    static id = "richCarouselOption";
    /** @type {import("plugins").WebsiteResources} */
    resources = {
        builder_options: [withSequence(RICH_CAROUSEL, RichCarouselOption)],
        builder_actions: {
            RichCarouselToggleAction,
            RichCarouselVarAction,
            RichCarouselFreezeHeightAction,
            RichCarouselMatchImageAction,
        },
    };
}

/**
 * Turns the banner options on or off. Off, they're all removed, not only
 * their effect, so that the carousel is back to what it was.
 */
export class RichCarouselToggleAction extends BuilderAction {
    static id = "richCarouselToggle";
    isApplied({ editingElement }) {
        return editingElement.classList.contains("o_rich_carousel");
    }
    apply({ editingElement }) {
        editingElement.classList.add("o_rich_carousel");
    }
    clean({ editingElement }) {
        const optionClasses = [...editingElement.classList].filter((className) =>
            className.startsWith("o_rc_")
        );
        editingElement.classList.remove("o_rich_carousel", ...optionClasses);
        for (const property of [...editingElement.style]) {
            if (property.startsWith("--o-rc-")) {
                editingElement.style.removeProperty(property);
            }
        }
        for (const key of ["bsPause", "bsWrap", "bsTouch"]) {
            delete editingElement.dataset[key];
        }
    }
}

/**
 * Sets a CSS variable of the carousel, or removes it when the value is empty
 * (e.g. the tablet height, to fall back on the desktop one).
 */
export class RichCarouselVarAction extends BuilderAction {
    static id = "richCarouselVar";
    getValue({ editingElement, params: { mainParam: property } }) {
        return editingElement.style.getPropertyValue(property).trim();
    }
    apply({ editingElement, params: { mainParam: property }, value }) {
        if (value) {
            editingElement.style.setProperty(property, value);
        } else {
            editingElement.style.removeProperty(property);
        }
    }
}

/**
 * Switching to a fixed height starts from the current height of the banner,
 * so that it doesn't jump.
 */
export class RichCarouselFreezeHeightAction extends BuilderAction {
    static id = "richCarouselFreezeHeight";
    async load({ editingElement }) {
        // Measured before the fixed height applies.
        return editingElement.querySelector(":scope > .carousel-inner")?.offsetHeight;
    }
    apply({ editingElement, loadResult: height }) {
        if (height && !editingElement.style.getPropertyValue("--o-rc-height")) {
            editingElement.style.setProperty("--o-rc-height", `${height}px`);
        }
    }
}

/**
 * Gives the banner the ratio of the image of the shown slide (or of its
 * background image), so that it's shown whole, neither cropped nor stretched.
 */
export class RichCarouselMatchImageAction extends BuilderAction {
    static id = "richCarouselMatchImage";
    async load({ editingElement }) {
        const slideEl =
            editingElement.querySelector(".carousel-item.active") ||
            editingElement.querySelector(".carousel-item");
        const src = slideEl && getSlideImageSrc(slideEl);
        if (!src) {
            return;
        }
        const imageEl = this.document.createElement("img");
        imageEl.src = src;
        try {
            await imageEl.decode();
        } catch {
            return;
        }
        return { width: imageEl.naturalWidth, height: imageEl.naturalHeight };
    }
    apply({ editingElement, loadResult }) {
        if (loadResult?.width && loadResult?.height) {
            editingElement.style.setProperty(
                "--o-rc-ratio",
                `${loadResult.width} / ${loadResult.height}`
            );
        }
    }
    clean({ editingElement }) {
        editingElement.style.removeProperty("--o-rc-ratio");
    }
}

function getSlideImageSrc(slideEl) {
    const imageEl = slideEl.querySelector("img");
    if (imageEl) {
        return imageEl.getAttribute("src");
    }
    const backgroundImage = slideEl.ownerDocument.defaultView.getComputedStyle(slideEl)
        .backgroundImage;
    return backgroundImage.match(/url\(["']?(.*?)["']?\)/)?.[1];
}

registry.category("website-plugins").add(RichCarouselOptionPlugin.id, RichCarouselOptionPlugin);
