from odoo import models


class ProductTag(models.Model):
    _inherit = 'product.tag'

    def _update_field_translations(self, field_name, translations, digest=None, source_lang=''):
        # The translation window writes the translations in SQL, without
        # recomputing what depends on them, like the tags' names on products
        result = super()._update_field_translations(field_name, translations, digest=digest, source_lang=source_lang)
        if field_name == 'name':
            self.modified(['name'])
        return result
