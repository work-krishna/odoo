# -*- coding: utf-8 -*-
from odoo import Command

# Community defaults restored when ci_account is uninstalled.
_COMMUNITY_GROUP_NAMES = {
    'account.group_account_readonly': 'Show Accounting Features - Readonly',
    'account.group_account_user': 'Show Full Accounting Features',
}


def _ci_account_post_init(env):
    """Companies that exist before the install get the per-company defaults."""
    env['res.company'].search([])._ci_account_setup_company()


def _ci_account_uninstall(env):
    """Hand the accounting groups and the app menu back to Community."""
    for xmlid, name in _COMMUNITY_GROUP_NAMES.items():
        group = env.ref(xmlid, raise_if_not_found=False)
        if group:
            group.write({'name': name, 'privilege_id': False})
    manager = env.ref('account.group_account_manager', raise_if_not_found=False)
    user = env.ref('account.group_account_user', raise_if_not_found=False)
    if manager and user:
        manager.write({'implied_ids': [Command.unlink(user.id)]})
    menu = env.ref('account.menu_finance', raise_if_not_found=False)
    if menu:
        menu.write({'name': 'Invoicing', 'web_icon': 'account,static/description/icon.png'})
