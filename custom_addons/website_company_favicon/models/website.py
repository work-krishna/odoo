import base64
import io
import logging

from PIL import Image

from odoo import api, fields, models
from odoo.tools.image import ImageProcess

_logger = logging.getLogger(__name__)

ICON_SIZES = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]


def _logo_icon(logo):
    """The logo (base64) as a favicon (base64): trimmed of transparent borders
    and centred in a transparent square, as a multi-size ICO file. An SVG logo
    is used as it is; an unreadable one gives no favicon."""
    data = base64.b64decode(logo)
    if data.lstrip()[:1] == b'<':  # SVG, which browsers show as a favicon directly
        return logo
    image = ImageProcess(data).image
    if not image:
        return False
    image = image.convert('RGBA')
    image = image.crop(image.getbbox() or (0, 0, image.width, image.height))
    scale = 256 / max(image.size)  # up or down, so every icon size is drawn from 256 px
    image = image.resize((max(1, round(image.width * scale)), max(1, round(image.height * scale))), Image.LANCZOS)
    square = Image.new('RGBA', (256, 256), (0, 0, 0, 0))
    square.paste(image, ((256 - image.width) // 2, (256 - image.height) // 2))
    output = io.BytesIO()
    square.save(output, format='ICO', sizes=ICON_SIZES)
    return base64.b64encode(output.getvalue())


class Website(models.Model):
    _inherit = 'website'

    favicon = fields.Binary(
        compute='_compute_favicon', store=True, readonly=True,
        help="The logo of the company this website belongs to; empty when that company has no logo of its own.",
    )
    # Pages check this instead of reading the favicon file on every request.
    has_company_favicon = fields.Boolean(compute='_compute_favicon', store=True)

    @api.depends('company_id.logo', 'company_id.uses_default_logo')
    def _compute_favicon(self):
        for website in self:
            company = website.company_id.sudo()
            favicon = False
            if company.logo and not company.uses_default_logo:
                try:
                    favicon = _logo_icon(company.logo)
                except Exception:  # a logo Odoo accepted but PIL cannot turn into an icon
                    _logger.warning("Could not make a favicon out of the logo of %s", company.name, exc_info=True)
            website.favicon = favicon
            website.has_company_favicon = bool(favicon)

    @api.model_create_multi
    def create(self, vals_list):
        websites = super().create(vals_list)
        # The field's original default (Odoo's icon) fills it at creation: compute it now.
        self.env.add_to_compute(self._fields['favicon'], websites)
        self.env.add_to_compute(self._fields['has_company_favicon'], websites)
        return websites

    @api.model
    def _handle_favicon(self, vals):
        # Only the company logo is used: ignore favicons written directly (settings, website creation).
        vals.pop('favicon', None)
