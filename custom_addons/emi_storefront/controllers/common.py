# -*- coding: utf-8 -*-
import base64

from werkzeug.exceptions import NotFound

from odoo.http import request
from odoo.tools.mimetypes import guess_mimetype

DOCUMENT_MIMETYPES = {'image/jpeg', 'image/png', 'image/webp', 'application/pdf'}
IMAGE_MIMETYPES = {'image/jpeg', 'image/png', 'image/webp'}
MAX_UPLOAD_BYTES = 10 * 1024 * 1024


class UploadError(ValueError):
    """A customer-facing problem with an uploaded file."""


def get_phone(slug):
    """Published phone for a '/phones/<slug>' URL, or 404."""
    _name, tmpl_id = request.env['ir.http']._unslug(slug)
    phone = request.env['product.template'].sudo().browse(tmpl_id or 0).exists()
    if not phone or not phone._emi_is_on_storefront():
        raise NotFound()
    return phone


def phone_url(phone):
    return f"/phones/{request.env['ir.http']._slug(phone)}"


def read_upload(upload, label, allowed=DOCUMENT_MIMETYPES, required=True):
    """Return the uploaded file as base64 after checking its size and real type."""
    if not upload or not getattr(upload, 'filename', None):
        if required:
            raise UploadError(f"Please upload the {label}.")
        return False
    data = upload.read(MAX_UPLOAD_BYTES + 1)
    if not data:
        raise UploadError(f"The {label} file is empty.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise UploadError(f"The {label} is larger than {MAX_UPLOAD_BYTES // (1024 * 1024)} MB.")
    if guess_mimetype(data) not in allowed:
        kinds = 'a JPEG, PNG or WebP image' if allowed == IMAGE_MIMETYPES else 'a JPEG, PNG, WebP or PDF file'
        raise UploadError(f"The {label} must be {kinds}.")
    return base64.b64encode(data)


def to_float(value, default=0.0):
    try:
        return float(str(value).replace(',', '')) if value not in (None, '') else default
    except ValueError:
        return default


def to_int(value):
    try:
        return int(value) if value not in (None, '') else None
    except (TypeError, ValueError):
        return None


def current_vendor():
    """The approved-or-pending retailer the logged-in portal user works for."""
    user = request.env.user
    if user._is_public():
        return request.env['emi.vendor']
    return request.env['emi.vendor'].sudo().search([('user_ids', 'in', user.id)], limit=1)
