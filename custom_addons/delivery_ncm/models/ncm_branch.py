# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging
import re

from odoo import api, fields, models

from odoo.addons.delivery_ncm import const
from odoo.addons.delivery_ncm.models.ncm_request import NcmClient, NcmError

_logger = logging.getLogger(__name__)


def normalize_name(text):
    """Upper-case, single-spaced text used to compare NCM names with address parts."""
    return ' '.join(re.sub(r'[^A-Za-z0-9()/&.\- ]+', ' ', text or '').upper().split()).strip(' .-')


def split_areas(areas_covered):
    names = []
    for part in (areas_covered or '').split(','):
        name = normalize_name(part)
        if name and name not in names:
            names.append(name)
    return names


def parse_geocode(geocode):
    try:
        lat, lon = (float(part) for part in (geocode or '').split(','))
    except ValueError:
        return 0.0, 0.0
    # Rounded like the fields store them, or every sync would see a change.
    return round(lat, 7), round(lon, 7)


class NcmBranch(models.Model):
    _name = 'ncm.branch'
    _description = "NCM Branch"
    _order = 'name'
    _rec_names_search = ['name', 'code', 'district']

    name = fields.Char(
        required=True, index=True,
        help="Branch name exactly as NCM spells it; NCM matches branches by this name.",
    )
    ncm_id = fields.Integer(string="NCM ID", help="Branch ID on NCM's production server.")
    code = fields.Char()
    branch_type = fields.Char(string="Type", help="'Branch' or 'Logistics', as NCM labels it.")
    district = fields.Char(index=True)
    province = fields.Char()
    address = fields.Char()
    phone = fields.Char()
    phone2 = fields.Char(string="Other Phones")
    surcharge = fields.Float()
    latitude = fields.Float(digits=(10, 7))
    longitude = fields.Float(digits=(10, 7))
    area_ids = fields.One2many('ncm.area', 'branch_id', string="Areas Covered")
    area_count = fields.Integer(compute='_compute_area_count')
    active = fields.Boolean(default=True)

    _name_uniq = models.Constraint('UNIQUE(name)', "An NCM branch with this name already exists.")

    @api.depends('name', 'district')
    def _compute_display_name(self):
        for branch in self:
            district = (branch.district or '').title()
            branch.display_name = f"{branch.name} ({district})" if district else branch.name

    def _ncm_pickup_location_values(self):
        """This branch shaped like the pickup locations Odoo's location selector expects."""
        self.ensure_one()
        return {
            'id': self.id,
            'name': self.env._("NCM %s", self.name.title()),
            'street': self.address or '',
            'city': (self.district or '').title(),
            'state': '',
            'zip_code': '',
            'country_code': 'NP',
            'latitude': self.latitude,
            'longitude': self.longitude,
            'opening_hours': {},
        }

    def _compute_area_count(self):
        counts = dict(self.env['ncm.area']._read_group(
            [('branch_id', 'in', self.ids)], ['branch_id'], ['__count'],
        ))
        for branch in self:
            branch.area_count = counts.get(branch, 0)

    # Sync ----------------------------------------------------------------------------------

    @api.model
    def _ncm_sync(self, client=None):
        """Refresh branches and their covered areas from NCM's public branch list."""
        client = client or NcmClient(const.API_URLS[const.BRANCH_SOURCE_ENVIRONMENT])
        rows = client.get_branches()
        if not rows:
            raise NcmError("NCM returned an empty branch list.")
        return self._ncm_apply_branch_rows(rows)

    @api.model
    def _ncm_branch_values(self, row):
        latitude, longitude = parse_geocode(row.get('geocode'))
        return {
            # Kept verbatim: NCM looks branches up by exact name.
            'name': (row.get('name') or '').strip(),
            'ncm_id': row.get('pk') or 0,
            'code': (row.get('code') or '').strip() or False,
            'branch_type': (row.get('branch_type') or '').strip() or False,
            'district': normalize_name(row.get('district_name')) or False,
            'province': normalize_name(row.get('province_name')) or False,
            'address': (row.get('address') or '').strip() or False,
            'phone': (row.get('phone') or '').strip() or False,
            'phone2': (row.get('phone2') or '').strip() or False,
            'surcharge': round(float(row.get('surcharge') or 0.0), 2),
            'latitude': latitude,
            'longitude': longitude,
            'active': True,
        }

    @api.model
    def _ncm_apply_branch_rows(self, rows):
        Branch = self.with_context(active_test=False)
        existing = {branch.name: branch for branch in Branch.search([])}
        values_by_name = {}
        for row in rows:
            values = self._ncm_branch_values(row)
            if values['name'] and values['name'] not in values_by_name:
                values_by_name[values['name']] = (values, split_areas(row.get('areas_covered')))

        created = updated = 0
        to_create = []
        for name, (values, _areas) in values_by_name.items():
            branch = existing.get(name)
            if not branch:
                to_create.append(values)
                continue
            changes = {key: value for key, value in values.items() if branch[key] != value}
            if changes:
                branch.write(changes)
                updated += 1
        if to_create:
            created = len(Branch.create(to_create))

        stale = Branch.search([('name', 'not in', list(values_by_name)), ('active', '=', True)])
        stale.area_ids.active = False
        stale.active = False

        branches = Branch.search([('name', 'in', list(values_by_name))])
        self.env['ncm.area']._ncm_apply_areas({
            branch: values_by_name[branch.name][1] for branch in branches
        })
        _logger.info("NCM branch sync: %s created, %s updated, %s archived", created, updated, len(stale))
        return {'created': created, 'updated': updated, 'archived': len(stale)}


class NcmArea(models.Model):
    _name = 'ncm.area'
    _description = "NCM Delivery Area"
    _order = 'name, branch_id'
    _rec_names_search = ['name', 'branch_id.name', 'district']

    name = fields.Char(required=True, index=True)
    branch_id = fields.Many2one('ncm.branch', string="Branch", required=True, index=True, ondelete='cascade')
    district = fields.Char(related='branch_id.district', store=True)
    active = fields.Boolean(default=True)

    _name_branch_uniq = models.Constraint(
        'UNIQUE(name, branch_id)', "This area is already listed for that branch.",
    )

    @api.depends('name', 'branch_id.name', 'district')
    def _compute_display_name(self):
        for area in self:
            district = (area.district or '').title()
            location = f"{area.name}, {district}" if district else area.name
            area.display_name = f"{location} – {area.branch_id.name}" if area.branch_id else location

    @api.model
    def _ncm_apply_areas(self, names_by_branch):
        """Make each branch's areas match `names_by_branch` ({branch: [area names]})."""
        Area = self.with_context(active_test=False)
        branches = self.env['ncm.branch'].union(*names_by_branch)
        existing = {(area.branch_id.id, area.name): area for area in Area.search([('branch_id', 'in', branches.ids)])}
        wanted = set()
        to_create = []
        for branch, names in names_by_branch.items():
            for name in names:
                key = (branch.id, name)
                wanted.add(key)
                if key not in existing:
                    to_create.append({'name': name, 'branch_id': branch.id})
        if to_create:
            Area.create(to_create)
        Area.union(*(area for key, area in existing.items() if key in wanted and not area.active)).active = True
        Area.union(*(area for key, area in existing.items() if key not in wanted and area.active)).active = False

    # Address matching ------------------------------------------------------------------------

    @api.model
    def _ncm_match_partner(self, partner):
        """Best-effort guess of the NCM branch delivering to `partner`'s address.

        Returns an empty recordset when the address is ambiguous: many area names exist under
        several branches, so a wrong guess is worse than asking someone to pick the area.
        """
        Branch = self.env['ncm.branch']
        tokens = []
        for text in (partner.street2, partner.street, partner.city):
            for part in (text or '').split(','):
                token = normalize_name(part)
                # "Lakeside-6", "Baneshwor 10": drop the ward number too.
                for candidate in (token, re.sub(r'[\s\-]*\d+$', '', token).strip()):
                    if candidate and not candidate.isdigit() and candidate not in tokens:
                        tokens.append(candidate)
        tokens = tokens[:12]

        # 1. An area named in the address; a shared area name needs its district or branch named too.
        for token in tokens:
            branches = self.search([('name', '=', token)]).branch_id
            if len(branches) > 1:
                branches = branches.filtered(lambda b: b.district in tokens or b.name in tokens)
            if len(branches) == 1:
                return branches
        # 2. A branch named in the address.
        branches = Branch.search([('name', 'in', tokens)])
        if len(branches) == 1:
            return branches
        # 3. A district served by a single NCM branch.
        city = normalize_name(partner.city)
        if city:
            branches = Branch.search([('district', '=', city), ('branch_type', '=', 'Branch')])
            if len(branches) == 1:
                return branches
        return Branch
