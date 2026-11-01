import { BaseOptionComponent } from "@html_builder/core/utils";

export class RichCarouselOption extends BaseOptionComponent {
    static template = "website_rich_carousel.RichCarouselOption";
    static selector = "section";
    static applyTo = ":scope > .s_carousel";
}
