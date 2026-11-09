import os
from unittest import skipUnless

from django.conf import settings
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import Client, override_settings
from django.urls import reverse

from . import test_account_deactivation as fixtures


@skipUnless(os.environ.get('DEPARTMENT_BROWSER_TESTS') == '1', 'Opt-in browser verification')
@override_settings(SESSION_ENGINE='django.contrib.sessions.backends.signed_cookies',
                   EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class DeactivationBrowserTests(StaticLiveServerTestCase):
    def setUp(self):
        fixtures.AccountDeactivationTests.setUp(self)
        self.admin_cookie = self.client.cookies[settings.SESSION_COOKIE_NAME].value
        head_client = Client()
        head_client.force_login(self.head)
        self.head_cookie = head_client.cookies[settings.SESSION_COOKIE_NAME].value

    def test_warnings_cancel_and_processing_prevent_duplicate_submissions(self):
        from playwright.sync_api import sync_playwright
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            context = browser.new_context()
            context.add_cookies([{'name': settings.SESSION_COOKIE_NAME, 'value': self.admin_cookie, 'url': self.live_server_url}])
            page = context.new_page()
            page.goto(self.live_server_url + reverse('superadmin:manage_faculty'))
            warnings = []
            page.on('dialog', lambda dialog: (warnings.append(dialog.message), dialog.dismiss()))
            page.get_by_role('button', name='Deactivate', exact=True).click()
            self.assertIn('1 consultation record(s) will be preserved', warnings[-1])
            self.assertIn('Login and new booking access will be removed', warnings[-1])
            page.goto(self.live_server_url + reverse('superadmin:manage_students'))
            page.get_by_role('button', name='Deactivate', exact=True).click()
            self.assertIn('1 consultation record(s) will be preserved', page.locator('#studentAccessWarning').inner_text())
            page.locator('#cancelRemoveStudentSA').click()
            self.assertFalse(page.locator('#removeStudentSAModal').is_visible())
            # Hold the request so a second click cannot submit another action.
            submitted = []
            page.route('**/students/*/remove/', lambda route: submitted.append(route))
            page.get_by_role('button', name='Deactivate', exact=True).click()
            page.locator('#confirmRemoveStudentSA').click()
            page.wait_for_timeout(150)
            self.assertTrue(page.locator('#confirmRemoveStudentSA').is_disabled())
            self.assertEqual(len(submitted), 1)
            submitted[0].fulfill(status=500, content_type='application/json', body='{"success":false,"error":"test failure"}')
            page.wait_for_timeout(150)
            self.assertFalse(page.locator('#confirmRemoveStudentSA').is_disabled())
            context.clear_cookies()
            context.add_cookies([{'name': settings.SESSION_COOKIE_NAME, 'value': self.head_cookie, 'url': self.live_server_url}])
            page.goto(self.live_server_url + reverse('depthead:admin_faculty'))
            page.get_by_role('button', name='Deactivate', exact=True).click()
            self.assertIn('1 consultation record(s) will be preserved', page.locator('#facultyAccessWarning').inner_text())
            self.assertNotIn('cannot be undone', page.locator('#removeFacultyConfirmModal').inner_text())
            page.locator('#closeRemoveFacultyConfirm').click()
            self.assertFalse(page.locator('#removeFacultyConfirmModal').is_visible())
            browser.close()
