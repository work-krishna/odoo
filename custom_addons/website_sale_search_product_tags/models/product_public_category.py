from odoo import api, fields, models


class ProductPublicCategory(models.Model):
    _inherit = 'product.public.category'

    product_tag_ids = fields.Many2many(
        comodel_name='product.tag', relation='product_public_category_product_tag_rel', string="Tags",
        help="Searching one of these tags on the website finds the products of this category and of its "
             "subcategories, without having to tag each of them",
    )
    # Stored, so that a change of a category also updates the products of its
    # subcategories
    website_search_keywords = fields.Char(
        compute='_compute_website_search_keywords', store=True, recursive=True,
        help="Technical field: the names, in every language, of the category, of its parents and of their tags "
             "customers can see, for the website search of their products",
    )

    @api.depends('name', 'product_tag_ids.name', 'product_tag_ids.visible_to_customers', 'parent_id.website_search_keywords')
    def _compute_website_search_keywords(self):
        langs = [code for code, _name in self.env['res.lang'].get_installed()]
        for category in self:
            tags = category.product_tag_ids.filtered('visible_to_customers')
            parent_keywords = category.parent_id.website_search_keywords
            names = set(parent_keywords.split(', ') if parent_keywords else ())
            for lang in langs:
                names.add(category.with_context(lang=lang).name)
                names.update(tags.with_context(lang=lang).mapped('name'))
            category.website_search_keywords = ', '.join(sorted(name for name in names if name)) or False

    def _update_field_translations(self, field_name, translations, digest=None, source_lang=''):
        # The translation window writes the translations in SQL, without
        # recomputing what depends on them, like the keywords of the products
        result = super()._update_field_translations(field_name, translations, digest=digest, source_lang=source_lang)
        if field_name == 'name':
            self.modified(['name'])
        return result
