# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo.exceptions import UserError
from odoo.tests import tagged

from odoo.addons.sms_nestsms.tests.common import NestSmsCommon, fake_response

LOGIN_TEXT = "Flagship-Store: Your OTP for login is {otp}. It is valid for 10 minutes. Never share this code with anyone."
APPROVED_ID = '11111111-1111-4111-8111-111111111111'
PENDING_ID = '22222222-2222-4222-8222-222222222222'


def template(id_, name, verified=True, content=LOGIN_TEXT, message_type='otp', with_content=True):
    values = {'id': id_, 'name': name, 'message_type': message_type, 'is_active': True, 'is_verified': verified}
    if with_content:
        values['content'] = content
    return values


def list_reply(templates, total=None, offset=0):
    return fake_response(200, {'success': True, 'templates': templates, 'pagination': {
        'total': len(templates) if total is None else total, 'limit': 10, 'offset': offset,
    }})


def detail_reply(values):
    return fake_response(200, {'success': True, 'template': values})


@tagged('post_install', '-at_install')
class TestTemplatePicker(NestSmsCommon):

    def _open(self, purpose='login'):
        action = self.env['res.config.settings'].create({}).with_context(
            sms_otp_purpose=purpose).action_sms_otp_choose_template()
        return self.env[action['res_model']].browse(action['res_id'])

    def test_lists_otp_templates(self):
        self.nestsms.replies = [
            list_reply([
                template(PENDING_ID, "Login (new)", verified=False, with_content=False),
                template(APPROVED_ID, "Login"),
                template('33333333-3333-4333-8333-333333333333', "Order note", message_type='transactional'),
            ]),
            detail_reply(template(PENDING_ID, "Login (new)", verified=False, content="Flagship-Store: Code {otp}")),
        ]
        picker = self._open()
        self.assertFalse(picker.error)
        self.assertEqual(picker.line_ids.mapped('nestsms_id'), [APPROVED_ID, PENDING_ID], "OTP only, approved first.")
        self.assertEqual(picker.line_ids[1].content, "Flagship-Store: Code {otp}", "Text fetched when the list leaves it out.")
        self.assertTrue(all(picker.line_ids.mapped('is_brand_ok')))
        self.assertEqual(
            [call['path'] for call in self.nestsms.calls],
            ['/sms/templates?offset=0&message_type=otp', f'/sms/templates/{PENDING_ID}'],
        )

    def test_follows_pagination(self):
        first = [template(f'00000000-0000-4000-8000-0000000000{i:02d}', f"T{i:02d}") for i in range(10)]
        second = [template(f'00000000-0000-4000-8000-0000000000{i:02d}', f"T{i:02d}") for i in range(10, 12)]
        self.nestsms.replies = [list_reply(first, total=12), list_reply(second, total=12, offset=10)]
        picker = self._open()
        self.assertEqual(len(picker.line_ids), 12)
        self.assertEqual(self.nestsms.calls[1]['path'], '/sms/templates?offset=10&message_type=otp')

    def test_choosing_an_approved_template_turns_codes_on(self):
        self.nestsms.replies = [list_reply([template(APPROVED_ID, "Login")])]
        picker = self._open()
        self.nestsms.replies = [detail_reply(template(APPROVED_ID, "Login"))]  # the check
        action = picker.line_ids.action_use()
        self.assertEqual(action['params']['type'], 'success')
        self.assertEqual(action['params']['next'], {'type': 'ir.actions.act_window_close'})
        self.assertEqual(self.company.sms_otp_login_template, APPROVED_ID)
        self.assertTrue(self.company._sms_otp_enabled('login'))

    def test_choosing_a_pending_template_keeps_codes_off(self):
        self.nestsms.replies = [list_reply([template(PENDING_ID, "Login", verified=False)])]
        picker = self._open()
        self.nestsms.replies = [detail_reply(template(PENDING_ID, "Login", verified=False))]
        action = picker.line_ids.action_use()
        self.assertEqual(action['params']['type'], 'warning')
        self.assertIn("not approved", action['params']['message'])
        self.assertEqual(self.company.sms_otp_login_template, PENDING_ID)
        self.assertFalse(self.company._sms_otp_enabled('login'))

    def test_wrong_brand_is_flagged(self):
        self.nestsms.replies = [list_reply([template(APPROVED_ID, "Login", content="Your OTP is {otp}")])]
        self.assertFalse(self._open().line_ids.is_brand_ok)

    def test_ip_restricted_key_explained(self):
        self.nestsms.replies = [fake_response(403, {
            'success': False, 'error': "Access denied from this IP address", 'code': 'IP_RESTRICTED',
            'your_ip': '204.168.202.130',
        })]
        picker = self._open()
        self.assertFalse(picker.line_ids)
        self.assertIn('IP_RESTRICTED', picker.error)
        self.assertIn('204.168.202.130', picker.error)
        self.assertIn('whitelist', picker.error)

    def test_refresh(self):
        self.nestsms.replies = [list_reply([])]
        picker = self._open()
        self.assertFalse(picker.line_ids)
        self.nestsms.replies = [list_reply([template(APPROVED_ID, "Login")])]
        action = picker.action_refresh()
        self.assertEqual(action['res_id'], picker.id)
        self.assertEqual(len(picker.line_ids), 1)

    def test_needs_a_key(self):
        self.company.sms_nestsms_api_key = False
        with self.assertRaises(UserError):
            self._open()
