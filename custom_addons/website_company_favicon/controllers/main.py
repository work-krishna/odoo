from odoo import http
from odoo.http import request

from odoo.addons.website.controllers.main import Website


class CompanyFavicon(Website):

    @http.route()
    def favicon(self, **kw):
        # Without a company logo there is no favicon: say so rather than send Odoo's icon.
        if not request.website.has_company_favicon:
            return request.not_found()
        return super().favicon(**kw)
