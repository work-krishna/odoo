from odoo import api, fields, models
from odoo.exceptions import UserError

NO_BRAND_XMLID = 'product_brand.product_brand_no_brand'


class ProductBrand(models.Model):
    _name = 'product.brand'
    _description = 'Product Brand'
    _order = 'sequence, name, id'

    name = fields.Char(required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    product_tmpl_ids = fields.One2many('product.template', 'product_brand_id', string='Products')
    product_count = fields.Integer(compute='_compute_product_count', string='Number of Products')

    _name_uniq = models.Constraint('unique(name)', 'This brand already exists.')

    def init(self):
        # Installing this module gives the existing products the default brand. Odoo does that when it
        # adds product.template's column, which comes right after this table but before the data files
        # are loaded: so "No Brand" is created here. The data file then takes it over as a noupdate record.
        if not self._get_no_brand():
            no_brand = self.create({'name': 'No Brand', 'sequence': 0})
            self.env['ir.model.data']._update_xmlids([{'xml_id': NO_BRAND_XMLID, 'record': no_brand, 'noupdate': True}])

    @api.model
    def _get_no_brand(self):
        return self.env.ref(NO_BRAND_XMLID, raise_if_not_found=False) or self.browse()

    def _compute_product_count(self):
        counts = dict(self.env['product.template']._read_group(
            [('product_brand_id', 'in', self.ids)], ['product_brand_id'], ['__count'],
        ))
        for brand in self:
            brand.product_count = counts.get(brand, 0)

    def copy_data(self, default=None):
        vals_list = super().copy_data(default=default)
        return [dict(vals, name=self.env._("%s (copy)", brand.name)) for brand, vals in zip(self, vals_list)]

    def write(self, vals):
        # Products are created with it, so it has to stay available
        if 'active' in vals and not vals['active'] and self._get_no_brand() in self:
            raise UserError(self.env._("\"No Brand\" is the brand of new products, it cannot be archived."))
        return super().write(vals)

    @api.ondelete(at_uninstall=False)
    def _unlink_except_no_brand(self):
        if self._get_no_brand() in self:
            raise UserError(self.env._("\"No Brand\" is the brand of new products, it cannot be deleted."))

    def action_open_products(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('product.product_template_action_all')
        action.update(
            domain=[('product_brand_id', '=', self.id)],
            context={'default_product_brand_id': self.id},
            display_name=self.name,
        )
        return action
