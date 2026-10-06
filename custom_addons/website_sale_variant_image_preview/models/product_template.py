from odoo import models
from odoo.http import request


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    def _get_variant_image_previews(self):
        """ The image of the variants that have their own, to show when hovering an attribute value on the product page.
        The URL is the one of the variant's image on its product page, which the browser then has.

        :return: the image URLs, by the variant's combination (`combination_indices`)
        :rtype: dict
        """
        self.ensure_one()
        if len(self.product_variant_ids) < 2:
            return {}
        image_field = self.env['ir.qweb.field.image']
        # Only the size of the images is read
        variants = self.with_context(bin_size=True).product_variant_ids.filtered('image_variant_1920')
        previews = {}
        for variant in variants:
            url = image_field._get_src_urls(variant, 'image_1920', {'preview_image': 'image_1024'})[0]
            # As the src of the images of the page (CDN)
            previews[variant.combination_indices] = self.env['ir.http']._url_for(url) if request else url
        return previews
