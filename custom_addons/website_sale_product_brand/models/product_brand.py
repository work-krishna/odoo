from odoo import models

from odoo.addons.website_sale.const import SHOP_PATH


class ProductBrand(models.Model):
    _inherit = 'product.brand'

    def _get_shop_url(self):
        """ The shop, showing only the products of this brand """
        self.ensure_one()
        return f"{SHOP_PATH}?brand={self.env['ir.http']._slug(self)}"
