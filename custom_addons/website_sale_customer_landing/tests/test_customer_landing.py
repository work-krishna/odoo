import re

from odoo.tests import HttpCase, new_test_user, tagged


@tagged('post_install', '-at_install')
class TestCustomerLanding(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.customer = new_test_user(cls.env, login='landing_customer', password='landing-Pass-1',
                                     groups='base.group_portal')
        cls.employee = new_test_user(cls.env, login='landing_employee', password='landing-Pass-2',
                                     groups='base.group_user')

    def _login(self, login, password, **extra):
        page = self.url_open('/web/login').text
        csrf = re.search(r'name="csrf_token" value="([^"]+)"', page).group(1)
        return self.url_open('/web/login', data={'login': login, 'password': password, 'csrf_token': csrf, **extra})

    def _path(self, response):
        return response.url.removeprefix(self.base_url())

    def test_customer_lands_on_the_store(self):
        response = self._login('landing_customer', 'landing-Pass-1')
        self.assertEqual(self._path(response), '/')

    def test_page_that_asked_still_wins(self):
        response = self._login('landing_customer', 'landing-Pass-1', redirect='/shop/cart')
        self.assertEqual(self._path(response), '/shop/cart')

    def test_employee_goes_to_the_backend(self):
        response = self._login('landing_employee', 'landing-Pass-2')
        self.assertTrue(self._path(response).startswith('/odoo'), response.url)

    def test_shop_now_on_my_account(self):
        self.authenticate('landing_customer', 'landing-Pass-1')
        page = self.url_open('/my/home').text
        self.assertRegex(page, r'<a href="/shop" class="btn btn-primary[^"]*">\s*<i[^>]*/?>(</i>)?\s*Shop now')
