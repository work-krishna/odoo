import base64
import io

from PIL import Image

from odoo.tests import HttpCase, tagged


def _png(width, height, colour):
    output = io.BytesIO()
    Image.new('RGB', (width, height), colour).save(output, format='PNG')
    return base64.b64encode(output.getvalue())


@tagged('post_install', '-at_install')
class TestCompanyFavicon(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.website = cls.env.ref('website.default_website')
        cls.company = cls.website.company_id

    def _icon(self, website):
        return Image.open(io.BytesIO(base64.b64decode(website.favicon)))

    def test_favicon_is_the_company_logo(self):
        self.company.logo = _png(400, 100, 'red')
        icon = self._icon(self.website)
        self.assertEqual(icon.format, 'ICO')
        self.assertEqual(icon.size, (256, 256), "a wide logo is centred in a square icon")
        self.assertEqual(icon.convert('RGBA').getpixel((128, 128))[:3], (255, 0, 0))

        self.company.logo = _png(300, 300, 'blue')  # follows the logo
        self.assertEqual(self._icon(self.website).convert('RGBA').getpixel((128, 128))[:3], (0, 0, 255))

        self.website.write({'favicon': _png(64, 64, 'green')})  # only the logo is used
        self.assertEqual(self._icon(self.website).convert('RGBA').getpixel((128, 128))[:3], (0, 0, 255))

        page = self.url_open('/')
        self.assertIn(f'/web/image/website/{self.website.id}/favicon', page.text)
        self.assertNotIn('/web/static/img/favicon.ico', page.text)
        response = self.url_open('/favicon.ico', allow_redirects=False)
        self.assertIn(response.status_code, (301, 302))

    def test_no_company_logo_means_no_favicon(self):
        for logo in (False, self.company._get_logo()):  # none, or Odoo's placeholder
            self.company.logo = logo
            self.assertFalse(self.website.favicon)
            page = self.url_open('/')
            self.assertNotIn('rel="shortcut icon"', page.text)
            self.assertNotIn('apple-touch-icon', page.text)
            self.assertNotIn('/web/static/img/favicon.ico', page.text)
            self.assertEqual(self.url_open('/favicon.ico', allow_redirects=False).status_code, 404)

    def test_each_website_uses_its_own_company(self):
        other_company = self.env['res.company'].create({'name': 'Second Shop', 'logo': _png(120, 120, 'yellow')})
        website = self.env['website'].create({'name': 'Second Shop', 'company_id': other_company.id})
        self.assertEqual(self._icon(website).convert('RGBA').getpixel((128, 128))[:3], (255, 255, 0))
        website.company_id = self.env['res.company'].create({'name': 'No Logo Co', 'logo': False})
        self.assertFalse(website.favicon)

    def test_backend_keeps_its_icon(self):
        self.company.logo = False
        self.authenticate('admin', 'admin')
        self.assertIn('/web/static/img/favicon.ico', self.url_open('/odoo').text)
