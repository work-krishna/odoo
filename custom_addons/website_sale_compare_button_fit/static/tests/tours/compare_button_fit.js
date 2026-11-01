import { registry } from "@web/core/registry";

function check(condition, message) {
    if (!condition) {
        throw new Error(message);
    }
}

function parts() {
    const buttonEl = document.querySelector(".o_add_compare_dyn");
    const [iconEl, labelEl] = buttonEl.children;
    return {
        button: buttonEl.getBoundingClientRect(),
        icon: iconEl.getBoundingClientRect(),
        label: labelEl.getBoundingClientRect(),
    };
}

function setWidth(width) {
    const buttonEl = document.querySelector(".o_add_compare_dyn");
    buttonEl.style.setProperty("flex", "none");
    buttonEl.style.setProperty("width", width, "important");
}

// Below 992 px wide, where the button shows its name (on computers, Odoo
// hides it when the wishlist is installed)
registry.category("web_tour.tours").add("website_sale_compare_button_fit", {
    steps: () => [
        {
            content: "Large button",
            trigger: ".o_add_compare_dyn.btn-lg",
            run() {
                window.compareButtonHeight = parts().button.height;
                setWidth("400px");
            },
        },
        {
            content: "The name fits: shown next to the icon, in the button",
            trigger: ".o_add_compare_dyn.btn-lg[style*='400px']",
            run() {
                const { button, icon, label } = parts();
                check(label.left >= icon.right, "The name should be next to the icon");
                check(
                    label.top >= button.top && label.bottom <= button.bottom,
                    "The name should be in the button"
                );
                setWidth("64px");
            },
        },
        {
            content: "The name doesn't fit: only the icon, centered",
            trigger: ".o_add_compare_dyn.btn-lg[style*='64px']",
            run() {
                const { button, icon, label } = parts();
                check(
                    button.height === window.compareButtonHeight,
                    "The button should keep its height"
                );
                check(label.top >= button.bottom, "The name should be out of the button");
                const iconX = icon.left + icon.width / 2;
                const iconY = icon.top + icon.height / 2;
                check(
                    Math.abs(iconX - (button.left + button.width / 2)) <= 1.5,
                    "The icon should be centered horizontally"
                );
                check(
                    Math.abs(iconY - (button.top + button.height / 2)) <= 1.5,
                    "The icon should be centered vertically"
                );
            },
        },
    ],
});
