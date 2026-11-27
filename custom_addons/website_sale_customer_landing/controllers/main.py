from odoo.http import request

from odoo.addons.website.controllers.main import Website

LANDING_PAGE = '/'


class CustomerLanding(Website):

    def _login_redirect(self, uid, redirect=None):
        # Every way in (password, sign-up, activation code, SMS code) ends here. Customers go
        # back to the store rather than to their account page; a page that asked them to sign
        # in (redirect) still gets them back, and employees still go to the backend.
        if not redirect and not request.env['res.users'].browse(uid)._is_internal():
            redirect = LANDING_PAGE
        return super()._login_redirect(uid, redirect=redirect)
