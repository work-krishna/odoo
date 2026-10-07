from odoo import api, fields, models

# Products shown at once on the shop for each number of columns: full rows
SHOP_PPG_BY_PPR = {2: 40, 3: 48, 4: 48, 5: 50}


class Website(models.Model):
    _inherit = 'website'

    # For the default 3 columns
    shop_ppg = fields.Integer(default=SHOP_PPG_BY_PPR[3])

    @api.model
    def _with_shop_ppg(self, vals):
        """ Setting the columns of the shop (website editor, shop configurator, ...) sets its products per page """
        ppg = SHOP_PPG_BY_PPR.get(vals.get('shop_ppr'))
        return dict(vals, shop_ppg=ppg) if ppg else vals

    @api.model_create_multi
    def create(self, vals_list):
        return super().create([self._with_shop_ppg(vals) for vals in vals_list])

    def write(self, vals):
        return super().write(self._with_shop_ppg(vals))
