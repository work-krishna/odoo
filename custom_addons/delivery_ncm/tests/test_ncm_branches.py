# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo.tests import tagged

from odoo.addons.delivery_ncm.tests.common import BRANCH_ROWS, NcmCommon, fake_response


@tagged('post_install', '-at_install')
class TestNcmBranches(NcmCommon):

    def test_sync_reads_public_production_list(self):
        self.fake.routes[('GET', '/api/v2/branches')] = fake_response(200, BRANCH_ROWS)
        result = self.env['ncm.branch']._ncm_sync()
        self.assertEqual(result, {'created': 0, 'updated': 0, 'archived': 0})
        call = self.fake.calls[0]
        self.assertTrue(call['url'].startswith('https://portal.nepalcanmove.com/'))
        self.assertNotIn('Authorization', call['headers'])

    def test_branch_values(self):
        pokhara = self.branch_pokhara
        self.assertEqual(pokhara.district, 'KASKI')
        self.assertAlmostEqual(pokhara.latitude, 28.209)
        self.assertEqual(pokhara.display_name, 'POKHARA (Kaski)')
        # Areas are trimmed, upper-cased and de-duplicated per branch.
        self.assertEqual(sorted(pokhara.area_ids.mapped('name')), ['BAGBAZAR', 'LAKESIDE', 'MAHENDRAPUL'])
        sankhu = self.env['ncm.branch'].search([('name', '=', 'SANKHU')])
        self.assertEqual((sankhu.latitude, sankhu.surcharge, sankhu.area_count), (0.0, 50.0, 0))

    def test_resync_updates_and_archives(self):
        rows = [dict(row) for row in BRANCH_ROWS if row['name'] != 'SANKHU']
        rows[2]['areas_covered'] = 'LAKESIDE, CHIPLEDHUNGA'
        rows[2]['phone'] = '9801999999'
        result = self.env['ncm.branch']._ncm_apply_branch_rows(rows)
        self.assertEqual(result['archived'], 1)
        self.assertEqual(self.branch_pokhara.phone, '9801999999')
        self.assertEqual(sorted(self.branch_pokhara.area_ids.mapped('name')), ['CHIPLEDHUNGA', 'LAKESIDE'])
        self.assertFalse(self.env['ncm.branch'].search([('name', '=', 'SANKHU')]))

        # Coming back re-activates the same records instead of duplicating them.
        self.env['ncm.branch']._ncm_apply_branch_rows(BRANCH_ROWS)
        self.assertEqual(self.env['ncm.branch'].search_count([('name', '=', 'SANKHU')]), 1)
        self.assertIn('BAGBAZAR', self.branch_pokhara.area_ids.mapped('name'))

    def test_match_partner_address(self):
        Partner = self.env['res.partner']
        cases = [
            # (address values, expected branch)
            ({'city': 'Pokhara'}, self.branch_pokhara),             # city is a branch name
            ({'street2': 'Koteshwor', 'city': 'Kathmandu'}, self.branch_tinkune),  # unique area
            ({'street2': 'Bagbazar', 'city': 'Kathmandu'}, self.branch_newroad),   # shared area, district decides
            ({'street2': 'Bagbazar'}, self.env['ncm.branch']),     # shared area, no hint: don't guess
            ({'city': 'Kathmandu'}, self.env['ncm.branch']),       # district with several branches
            ({'street': 'Lakeside-6, Pokhara'}, self.branch_pokhara),
        ]
        for values, expected in cases:
            partner = Partner.create({'name': 'Test', **values})
            self.assertEqual(partner._ncm_get_dest_branch(), expected, values)

    def test_area_beats_guess(self):
        partner = self.env['res.partner'].create({'name': 'Test', 'city': 'Pokhara'})
        partner.ncm_area_id = self.env['ncm.area'].search([('name', '=', 'ASAN')])
        self.assertEqual(partner._ncm_get_dest_branch(), self.branch_newroad)
