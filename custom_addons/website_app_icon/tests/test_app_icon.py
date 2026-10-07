import base64
import io
from urllib.parse import urlparse

from PIL import Image

from odoo.tests import HttpCase, tagged


def _png(width, height, colour, margin=0, margin_colour=(0, 0, 0, 0)):
    """ A rectangle of the colour, with a margin around it (transparent by default) """
    image = Image.new('RGBA', (width + 2 * margin, height + 2 * margin), margin_colour)
    image.paste(Image.new('RGBA', (width, height), colour), (margin, margin))
    output = io.BytesIO()
    image.save(output, format='PNG')
    return base64.b64encode(output.getvalue())


@tagged('post_install', '-at_install')
class TestAppIcon(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.website = cls.env.ref('website.default_website')
        cls.company = cls.website.company_id
        cls.company.logo = _png(300, 100, 'red', margin=50)
        cls.other_company = cls.env['res.company'].create({'name': 'Flagship', 'logo': _png(200, 200, (20, 20, 20))})
        cls.other_website = cls.env['website'].create({'name': 'Flagship Store', 'company_id': cls.other_company.id})
        # The requests of the tests are on the domain of the first website
        cls.website.domain = urlparse(cls.base_url()).netloc

    def _image(self, url):
        response = self.url_open(url)
        self.assertEqual(response.status_code, 200, url)
        return Image.open(io.BytesIO(response.content))

    def _manifest(self):
        return self.url_open('/web/manifest.webmanifest').json()

    def test_icons(self):
        icon = Image.open(io.BytesIO(base64.b64decode(self.website.app_icon)))
        self.assertEqual((icon.format, icon.size, icon.mode), ('PNG', (512, 512), 'RGB'))
        self.assertEqual(icon.getpixel((256, 256)), (255, 0, 0))
        self.assertEqual(icon.getpixel((256, 5)), (255, 255, 255), "Transparent around the logo: on white")
        self.assertEqual(icon.getpixel((256 - 220, 256)), (255, 0, 0), "The logo without its margin, 90% of the icon")
        self.assertEqual(self.website.app_icon_background, '#ffffff')

        maskable = Image.open(io.BytesIO(base64.b64decode(self.website.app_icon_maskable)))
        self.assertEqual(maskable.size, (512, 512))
        self.assertEqual(maskable.getpixel((256, 256)), (255, 0, 0))
        self.assertEqual(maskable.getpixel((256 - 200, 256)), (255, 255, 255), "Smaller, within the circle phones keep")

        icon = Image.open(io.BytesIO(base64.b64decode(self.other_website.app_icon)))
        self.assertEqual(icon.getpixel((3, 3)), (20, 20, 20), "An opaque logo: on the colour of its edge")
        self.assertEqual(self.other_website.app_icon_background, '#141414')

        # A logo with an opaque white margin, like a JPEG: without its margin too
        self.company.logo = _png(100, 100, 'blue', margin=100, margin_colour='white')
        icon = Image.open(io.BytesIO(base64.b64decode(self.website.app_icon)))
        self.assertEqual(self.website.app_icon_background, '#ffffff')
        self.assertEqual(icon.getpixel((256 - 220, 256 - 220)), (0, 0, 255))
        self.assertEqual(icon.getpixel((5, 5)), (255, 255, 255))

    def test_manifest(self):
        manifest = self._manifest()
        self.assertEqual(manifest['name'], self.website.name)
        self.assertEqual(manifest['background_color'], '#ffffff')
        self.assertEqual(manifest['scope'], '/odoo', "The rest of Odoo's manifest is kept")
        unique = self.website.app_icon_unique
        self.assertEqual([(icon['src'], icon['sizes'], icon['purpose']) for icon in manifest['icons']], [
            (f'/web/image/website/{self.website.id}/app_icon/192x192?unique={unique}', '192x192', 'any'),
            (f'/web/image/website/{self.website.id}/app_icon?unique={unique}', '512x512', 'any'),
            (f'/web/image/website/{self.website.id}/app_icon_maskable/192x192?unique={unique}', '192x192', 'maskable'),
            (f'/web/image/website/{self.website.id}/app_icon_maskable?unique={unique}', '512x512', 'maskable'),
        ])
        for icon in manifest['icons']:
            image = self._image(icon['src'])
            self.assertEqual((image.format, f'{image.width}x{image.height}'), ('PNG', icon['sizes']))

        self.authenticate('admin', 'admin')
        self.assertEqual(self._manifest()['icons'], manifest['icons'], "The same for users as for visitors")

    def test_icon_follows_the_logo(self):
        unique = self.website.app_icon_unique
        self.company.logo = _png(100, 100, 'blue')
        self.assertNotEqual(self.website.app_icon_unique, unique, "A new address, so that it is downloaded again")
        self.assertEqual(self._image(self._manifest()['icons'][1]['src']).getpixel((256, 256)), (0, 0, 255))

        for logo in (False, self.company._get_logo()):  # none, or Odoo's placeholder
            self.company.logo = logo
            self.assertFalse(self.website.app_icon)
            manifest = self._manifest()
            self.assertEqual(manifest['name'], self.website.name)
            self.assertEqual(manifest['icons'][0]['src'], '/web/static/img/odoo-icon-192x192.png', "Odoo's icon")

    def test_each_domain_has_its_website(self):
        self.assertEqual(self._manifest()['name'], self.website.name)
        self.website.domain = False
        self.env.flush_all()  # the domain of a website is unique
        self.other_website.domain = urlparse(self.base_url()).netloc
        manifest = self._manifest()
        self.assertEqual(manifest['name'], 'Flagship Store')
        self.assertIn(f'/web/image/website/{self.other_website.id}/app_icon', manifest['icons'][0]['src'])

    def test_not_the_website_chosen_in_the_backend(self):
        self.authenticate('admin', 'admin')
        # The website switcher of the backend
        self.url_open(f'/website/force/{self.other_website.id}', allow_redirects=False)
        self.assertEqual(self._manifest()['name'], self.website.name)

    def test_backend_and_offline_pages(self):
        self.authenticate('admin', 'admin')
        page = self.url_open('/odoo').text
        self.assertIn(f'rel="apple-touch-icon" href="/web/image/website/{self.website.id}/app_icon/180x180?unique=', page)
        self.assertNotIn('odoo-icon-ios.png', page)
        self.assertIn(self.website.app_icon.decode(), self.url_open('/odoo/offline').text)

        self.company.logo = False
        self.assertIn('rel="apple-touch-icon" href="/web/static/img/odoo-icon-ios.png"', self.url_open('/odoo').text)
        self.assertEqual(self.url_open('/odoo/offline').status_code, 200)
