from odoo import api, models


class IrHttp(models.AbstractModel):
    _inherit = 'ir.http'

    @api.model
    def webclient_rendering_context(self):
        context = super().webclient_rendering_context()
        website = self.env['website']._get_app_website()
        if website.app_icon_unique:
            context['app_touch_icon_url'] = website._get_app_icon_url(180)
        return context
