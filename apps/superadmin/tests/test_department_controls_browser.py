"""Opt-in browser checks for department checkboxes and settings columns."""
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest import skipUnless
from unittest.mock import patch

from django.conf import settings
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import override_settings
from django.urls import reverse

from apps.core.models import School, College, Department, DeptHeadInvite, User


@skipUnless(os.environ.get('DEPARTMENT_BROWSER_TESTS') == '1', 'Opt-in browser checks')
@override_settings(SESSION_ENGINE='django.contrib.sessions.backends.signed_cookies')
class DepartmentControlsBrowserTests(StaticLiveServerTestCase):
    def setUp(self):
        super().setUp()
        operator = User.objects.create_user(username='controls-operator', role='systemadmin')
        self.school = School(code='CONTROLS_UI', name='Controls test school')
        self.school.save(actor=operator)
        college = College.objects.create(school=self.school, code='CONTROLS', name='Controls college')
        self.first = Department.objects.create(school=self.school, college=college, code='DFIRST', name='Department of First Studies')
        self.second = Department.objects.create(school=self.school, code='DSECOND', name='Department of Second Studies')
        admin = User.objects.create_user(username='controls-admin', role='superadmin', school=self.school)
        self.head = User.objects.create_user(username='controls-head', role='depthead', school=self.school)
        self.head.managed_departments.add(self.first)
        self.client.force_login(admin)
        admin_cookie = self.client.cookies[settings.SESSION_COOKIE_NAME].value
        self.client.force_login(self.head)
        self.head_cookie = self.client.cookies[settings.SESSION_COOKIE_NAME].value
        from playwright.sync_api import sync_playwright
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch()
        self.context = self.browser.new_context(viewport={'width': 1360, 'height': 900})
        self.context.route('**/*', lambda route: route.continue_() if route.request.url.startswith(self.live_server_url) else route.abort())
        self.context.add_cookies([{'name': settings.SESSION_COOKIE_NAME, 'value': admin_cookie, 'url': self.live_server_url}])
        self.page = self.context.new_page()
        self.errors = []
        self.page.on('pageerror', lambda error: self.errors.append(str(error)))

    def tearDown(self):
        try:
            self.browser.close()
            self.playwright.stop()
        finally:
            super().tearDown()

    def database(self, callback):
        with ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(callback).result()

    def visit(self, name):
        self.page.goto(self.live_server_url + reverse(name))

    def screenshot(self, name):
        folder = Path(settings.BASE_DIR) / '.staging-backups' / 'department-controls'
        folder.mkdir(parents=True, exist_ok=True)
        self.page.screenshot(path=str(folder / name), full_page=True)

    def test_invite_with_two_checkboxes_and_reset_on_reopen(self):
        from playwright.sync_api import expect
        self.visit('superadmin:manage_admins')
        self.page.get_by_role('button', name='Invite Head', exact=True).click()
        dialog = self.page.locator('#headInviteModal')
        expect(dialog.locator('select[name=departments]')).to_have_count(0)
        expect(dialog).not_to_contain_text('Hold Ctrl')
        dialog.locator('[name=email]').fill('controls-invite@example.invalid')
        for department in (self.first, self.second):
            dialog.locator(f'input[name=departments][value="{department.pk}"]').check()
        self.screenshot('department-checkboxes.png')
        with patch('apps.superadmin.views.send_depthead_invite_email'):
            dialog.get_by_role('button', name='Save and Send Invite').click()
            expect(self.page.get_by_role('cell', name='controls-invite@example.invalid', exact=True)).to_be_visible()
        actual = self.database(lambda: set(DeptHeadInvite.objects.get(email='controls-invite@example.invalid').departments.values_list('pk', flat=True)))
        self.assertEqual(actual, {self.first.pk, self.second.pk})
        self.page.get_by_role('button', name='Invite Head', exact=True).click()
        expect(dialog.locator('input[name=departments]:checked')).to_have_count(0)
        self.assertFalse(self.errors)

    def test_edit_preselects_requires_one_and_saves_multiple_departments(self):
        from playwright.sync_api import expect
        self.visit('superadmin:manage_admins')
        self.page.get_by_role('button', name='Edit', exact=True).click()
        dialog = self.page.locator('#headEditModal')
        first = dialog.locator(f'input[name=departments][value="{self.first.pk}"]')
        second = dialog.locator(f'input[name=departments][value="{self.second.pk}"]')
        expect(first).to_be_checked()
        expect(second).not_to_be_checked()
        first.uncheck()
        self.assertFalse(dialog.locator('form').evaluate('(form) => form.checkValidity()'))
        self.assertEqual(first.evaluate('(input) => input.validationMessage'), 'Choose at least one department.')
        first.check()
        second.check()
        dialog.get_by_role('button', name='Save Assignments').click()
        expect(dialog).not_to_be_visible()
        actual = self.database(lambda: set(User.objects.get(pk=self.head.pk).managed_departments.values_list('pk', flat=True)))
        self.assertEqual(actual, {self.first.pk, self.second.pk})
        self.assertFalse(self.errors)

    def test_settings_details_above_booking_announcements_beside_details(self):
        from playwright.sync_api import expect
        self.database(lambda: User.objects.get(pk=self.head.pk).managed_departments.add(self.second))
        self.context.add_cookies([{'name': settings.SESSION_COOKIE_NAME, 'value': self.head_cookie, 'url': self.live_server_url}])
        self.visit('depthead:college_settings')
        expect(self.page.locator('.department-settings-unit')).to_have_count(2)
        expect(self.page.locator('.department-announcements')).to_have_count(1)
        unit = self.page.locator('.department-settings-unit').first
        details = unit.locator('.settings-card').nth(0).bounding_box()
        booking = unit.locator('.settings-card').nth(1).bounding_box()
        announcements = self.page.locator('.department-announcements').bounding_box()
        self.assertAlmostEqual(details['x'], booking['x'], delta=1)
        self.assertGreater(booking['y'], details['y'] + details['height'])
        self.assertGreater(announcements['x'], details['x'] + details['width'])
        self.assertAlmostEqual(announcements['y'], details['y'], delta=1)
        self.screenshot('settings-columns-desktop.png')
        self.page.set_viewport_size({'width': 390, 'height': 844})
        self.assertLessEqual(self.page.evaluate('document.documentElement.scrollWidth'), 391)
        last_unit = self.page.locator('.department-settings-unit').last.bounding_box()
        announcements = self.page.locator('.department-announcements').bounding_box()
        self.assertGreater(announcements['y'], last_unit['y'] + last_unit['height'])
        self.screenshot('settings-columns-mobile.png')
        self.assertFalse(self.errors)
