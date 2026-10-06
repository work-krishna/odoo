from odoo import models


class ProductProduct(models.Model):
    _inherit = 'product.product'

    def _set_image_1920(self):
        """ Override of `product`: an image given to one of the variants of a product is that variant's own, also when
        the product has no image yet; Odoo gives it to the product instead, i.e. to all its variants. It's then the
        product's image too, for its variants without their own image.
        """
        first_images = self.filtered(lambda variant: (
            variant.image_1920
            and not variant.product_tmpl_id.image_1920
            and len(variant.product_tmpl_id.product_variant_ids) > 1
        ))
        for variant in first_images:
            image = variant.image_1920
            variant.image_variant_1920 = image
            variant.product_tmpl_id.image_1920 = image
        return super(ProductProduct, self - first_images)._set_image_1920()
