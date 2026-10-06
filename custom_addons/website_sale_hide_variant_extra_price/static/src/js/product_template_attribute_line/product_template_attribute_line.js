import { patch } from '@web/core/utils/patch';
import {
    ProductTemplateAttributeLine,
} from '@sale/js/product_template_attribute_line/product_template_attribute_line';

patch(ProductTemplateAttributeLine.prototype, {
    /**
     * The options of a drop-down list: their name, without the extra price.
     *
     * @override
     */
    getPTAVSelectName(ptav) {
        return ptav.name;
    },
});
