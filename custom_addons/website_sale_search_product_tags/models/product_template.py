from odoo import api, fields, models


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    # Stored rather than searched through the tags, so that the search only
    # finds the tags customers can see, and so that its typo correction knows
    # the tags of the variants too (it only reads fields of the products and
    # of the records right next to them).
    website_tag_names = fields.Char(
        compute='_compute_website_tag_names', store=True, index='trigram',
        help="Technical field: the names, in every language, of the tags customers can see on the product "
             "or its variants, for the website search",
    )
    website_category_keywords = fields.Char(
        compute='_compute_website_category_keywords', store=True, index='trigram',
        help="Technical field: the names, in every language, of the eCommerce categories of the product, of their "
             "parents and of their tags customers can see, for the website search",
    )

    @api.depends(
        'product_tag_ids.name', 'product_tag_ids.visible_to_customers',
        'product_variant_ids.additional_product_tag_ids.name',
        'product_variant_ids.additional_product_tag_ids.visible_to_customers',
    )
    def _compute_website_tag_names(self):
        langs = [code for code, _name in self.env['res.lang'].get_installed()]
        for template in self:
            tags = template.product_tag_ids | template.product_variant_ids.additional_product_tag_ids
            tags = tags.filtered('visible_to_customers')
            names = {name for lang in langs for name in tags.with_context(lang=lang).mapped('name')}
            # Each name after a space: without pg_trgm, the typo correction
            # only knows the words at the start of a field or after a space
            template.website_tag_names = ', '.join(sorted(names)) or False

    @api.depends('public_categ_ids.website_search_keywords')
    def _compute_website_category_keywords(self):
        for template in self:
            names = {
                name
                for keywords in template.public_categ_ids.mapped('website_search_keywords') if keywords
                for name in keywords.split(', ')
            }
            template.website_category_keywords = ', '.join(sorted(names)) or False

    @api.model
    def _search_get_detail(self, website, order, options):
        detail = super()._search_get_detail(website, order, options)
        detail['search_fields'] += ['website_tag_names', 'website_category_keywords']
        detail['category_matches_last'] = options.get('categoryMatchesLast', True)
        return detail

    @api.model
    def _search_fetch(self, search_detail, search, limit, order):
        results, count = super()._search_fetch(search_detail, search, limit, order)
        if search and results and search_detail.get('category_matches_last'):
            # The products found by their own name, reference, tags... come
            # first, then the ones only found through their categories
            own_detail = dict(search_detail, search_fields=[
                field for field in search_detail['search_fields'] if field != 'website_category_keywords'
            ])
            own_results, _count = super()._search_fetch(own_detail, search, limit, order)
            results = (own_results | results)[:limit]
        return results, count
