from odoo import api, fields, models


class ProductPublicCategory(models.Model):
    _inherit = 'product.public.category'

    product_tag_ids = fields.Many2many(
        comodel_name='product.tag', relation='product_public_category_product_tag_rel', string="Tags",
        help="Searching one of these tags on the website finds the products of this category and of its "
             "subcategories, without having to tag each of them",
    )
    # Stored, so that a change of the tags of a category also updates the
    # products of its subcategories
    website_search_tag_ids = fields.Many2many(
        comodel_name='product.tag', relation='product_public_category_website_search_tag_rel',
        compute='_compute_website_search_tag_ids', store=True, recursive=True,
        help="Technical field: the tags of the category and of its parents, for the website search",
    )

    @api.depends('product_tag_ids', 'parent_id.website_search_tag_ids')
    def _compute_website_search_tag_ids(self):
        for category in self:
            category.website_search_tag_ids = category.product_tag_ids | category.parent_id.website_search_tag_ids
