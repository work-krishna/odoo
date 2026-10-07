from odoo import http
from odoo.http import request

from odoo.addons.web.controllers.webmanifest import WebManifest


class WebsiteWebManifest(WebManifest):

    def _get_webmanifest(self):
        manifest = super()._get_webmanifest()
        website = request.env['website']._get_app_website()
        manifest['name'] = website.name
        if website.app_icon_unique:
            manifest['background_color'] = website.app_icon_background
            manifest['icons'] = [{
                'src': website._get_app_icon_url(size, maskable=purpose == 'maskable'),
                'sizes': f'{size}x{size}',
                'type': 'image/png',
                'purpose': purpose,
            } for purpose in ('any', 'maskable') for size in (192, 512)]
        return manifest

    @http.route()
    def offline(self):
        website = request.env['website']._get_app_website()
        if not website.app_icon:
            return super().offline()
        return request.render('web.webclient_offline', {'odoo_icon': website.app_icon.decode()})
