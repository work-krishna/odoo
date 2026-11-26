# Part of Odoo. See LICENSE file for full copyright and licensing details.

from . import models

CORE_TEMPLATE = 'stock_sms.sms_template_data_stock_delivery'
OUR_TEMPLATE = 'sms_nestsms_stock.sms_template_shipped'


def _switch_template(env, from_xmlid, to_xmlid):
    old = env.ref(from_xmlid, raise_if_not_found=False)
    new = env.ref(to_xmlid, raise_if_not_found=False)
    if new:
        # Companies still on the old default (or on none); a template someone chose stays.
        companies = env['res.company'].search([('stock_sms_confirmation_template_id', 'in', [False, old.id] if old else [False])])
        companies.stock_sms_confirmation_template_id = new


def post_init_hook(env):
    _switch_template(env, CORE_TEMPLATE, OUR_TEMPLATE)


def uninstall_hook(env):
    _switch_template(env, OUR_TEMPLATE, CORE_TEMPLATE)
