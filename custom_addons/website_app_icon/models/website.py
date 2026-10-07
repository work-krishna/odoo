import base64
import hashlib
import io
import logging
import math

from PIL import Image, ImageChops

from odoo import api, fields, models
from odoo.http import request
from odoo.tools.image import ImageProcess

_logger = logging.getLogger(__name__)

ICON_SIZE = 512


def _edge_colour(image):
    """ The colour around the image (RGBA): the average of its opaque edge
    pixels, white when most of its edge is transparent """
    width, height = image.size
    edge = [(x, y) for x in range(width) for y in {0, height - 1}]
    edge += [(x, y) for y in range(1, height - 1) for x in {0, width - 1}]
    pixels = [image.getpixel(xy) for xy in edge]
    opaque = [pixel for pixel in pixels if pixel[3] >= 128]
    if len(opaque) * 2 < len(pixels):
        return (255, 255, 255)
    return tuple(round(sum(pixel[channel] for pixel in opaque) / len(opaque)) for channel in range(3))


def _content_box(image, background):
    """ The box of the logo in the image (RGBA): without the transparent or
    background-coloured margins around it (the noise of JPEGs aside) """
    flat = Image.new('RGB', image.size, background)
    flat.paste(image, mask=image)
    difference = ImageChops.difference(flat, Image.new('RGB', image.size, background)).convert('L')
    return difference.point(lambda value: 255 if value > 24 else 0).getbbox() or (0, 0, image.width, image.height)


def _square_icon(image, background, scale):
    """ The image resized by `scale` and centred on a square of the background
    colour, as a PNG (base64) """
    image = image.resize((max(1, round(image.width * scale)), max(1, round(image.height * scale))), Image.LANCZOS)
    square = Image.new('RGB', (ICON_SIZE, ICON_SIZE), background)
    square.paste(image, ((ICON_SIZE - image.width) // 2, (ICON_SIZE - image.height) // 2), image)
    output = io.BytesIO()
    square.save(output, format='PNG', optimize=True)
    return base64.b64encode(output.getvalue())


def _app_icons(logo):
    """ The icons of the app made out of the logo (base64), and their
    background colour: the logo on a square of the colour around it,
    - filling 90% of the icon, for any use;
    - within the circle of 80% of the icon for the maskable one, which phones
      crop to a circle or another shape.
    An SVG logo gives no icons. """
    image = ImageProcess(base64.b64decode(logo)).image
    if not image:
        return False, False, False
    image = image.convert('RGBA')
    background = _edge_colour(image)
    image = image.crop(_content_box(image, background))
    icon = _square_icon(image, background, 0.9 * ICON_SIZE / max(image.size))
    maskable = _square_icon(image, background, 0.8 * ICON_SIZE / math.hypot(*image.size))
    return icon, maskable, '#%02x%02x%02x' % background


class Website(models.Model):
    _inherit = 'website'

    app_icon = fields.Binary(
        compute='_compute_app_icon', store=True, readonly=True,
        help="The icon of the app installed from the website: the logo of its company. "
             "Empty when the company has no logo of its own.",
    )
    app_icon_maskable = fields.Binary(compute='_compute_app_icon', store=True, readonly=True)
    app_icon_background = fields.Char(compute='_compute_app_icon', store=True)
    # Changes with the icon, so that browsers and phones download it again
    app_icon_unique = fields.Char(compute='_compute_app_icon', store=True)

    @api.depends('company_id.logo', 'company_id.uses_default_logo')
    def _compute_app_icon(self):
        for website in self:
            company = website.company_id.sudo()
            icon = maskable = background = False
            if company.logo and not company.uses_default_logo:
                try:
                    icon, maskable, background = _app_icons(company.logo)
                except Exception:  # a logo Odoo accepted but PIL cannot read
                    _logger.warning("Could not make an app icon out of the logo of %s", company.name, exc_info=True)
            website.app_icon = icon
            website.app_icon_maskable = maskable
            website.app_icon_background = background
            website.app_icon_unique = icon and hashlib.sha1(icon).hexdigest()[:8]

    @api.model
    def _get_app_website(self):
        """ The website of the domain of the request. The app is the one of the
        domain it is installed from, while get_current_website() prefers the
        website last chosen in the backend. """
        website = self.sudo()
        return website.browse(website._get_current_website_id(request.httprequest.host if request else ''))

    def _get_app_icon_url(self, size=ICON_SIZE, maskable=False):
        self.ensure_one()
        field = 'app_icon_maskable' if maskable else 'app_icon'
        size_path = f'/{size}x{size}' if size != ICON_SIZE else ''
        return f'/web/image/website/{self.id}/{field}{size_path}?unique={self.app_icon_unique}'
