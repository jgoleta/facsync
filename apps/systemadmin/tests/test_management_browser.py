"""Opt-in real browser checks. Set SYSTEMADMIN_BROWSER_TESTS=1; install Playwright + Chromium locally."""
import importlib.util
import os
from pathlib import Path
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from django.conf import settings
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import override_settings

from apps.core.models import School, SchoolDomain, SuperAdminInvite, User


@unittest.skipUnless(os.getenv('SYSTEMADMIN_BROWSER_TESTS') == '1' and importlib.util.find_spec('playwright'),
                     'Opt-in Playwright browser tests; see docs/systemadmin-ui.md')
@override_settings(ALLOWED_HOSTS=['localhost', '127.0.0.1', 'testserver'])
class ManagementBrowserTests(StaticLiveServerTestCase):
    def setUp(self):
        from playwright.sync_api import expect, sync_playwright
        self.expect = expect
        self.operator = User.objects.create_user(username='browser-operator', role='systemadmin')
        self.school = School(name='North School', code='NORTH')
        self.school.save(actor=self.operator)
        SchoolDomain(school=self.school, domain='north.edu.ph').save(actor=self.operator)
        self.other = School(name='South School', code='SOUTH')
        self.other.save(actor=self.operator)
        self.admin = User.objects.create_user(username='browser-admin', first_name='Alex', last_name='Reyes',
            email='alex@example.invalid', role='superadmin', school=self.school)
        User.objects.create_user(username='browser-replacement', role='superadmin', school=self.school)
        self.invite = SuperAdminInvite.objects.create(email='invited@example.invalid', school=self.other,
                                                      invited_by=self.operator)
        self.client.force_login(self.operator)
        # Start Playwright only after synchronous Django fixtures. Stop it before
        # Django flushes the DB; its sync API runs an event loop on this thread.
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch(headless=True)
        self.context = self.browser.new_context(viewport={'width': 1440, 'height': 1000})
        self.context.add_cookies([{'name': settings.SESSION_COOKIE_NAME,
            'value': self.client.cookies[settings.SESSION_COOKIE_NAME].value, 'url': self.live_server_url}])
        self.context.route('**/*', lambda route: route.continue_() if route.request.url.startswith(self.live_server_url) else route.abort())
        self.page = self.context.new_page()
        self.errors = []
        self.page.on('pageerror', lambda error: self.errors.append(str(error)))
        self.mail_patch = patch('apps.systemadmin.views.send_superadmin_invite_email', return_value=True)
        self.mail_patch.start()

    def tearDown(self):
        self.context.close()
        self.browser.close()
        self.playwright.stop()
        self.mail_patch.stop()
        self.assertEqual(self.errors, [])
        super().tearDown()

    def school_count(self, code):
        with ThreadPoolExecutor(max_workers=1) as worker:
            return worker.submit(lambda: School.objects.filter(code=code).count()).result()

    def schools(self):
        self.page.goto(self.live_server_url + '/systemadmin/')

    def open_school(self):
        self.page.get_by_role('link', name='+ Add School').click()
        self.expect(self.page.locator('#system-form-modal input[name="name"]')).to_be_focused()
        return self.page.locator('#system-form-modal')

    def test_close_controls_and_focus_return(self):
        self.schools()
        for action in ('x', 'cancel', 'escape'):
            dialog = self.open_school()
            dialog.locator('input[name="name"]').fill('Unsaved School')
            if action == 'x': dialog.get_by_role('button', name='Close', exact=True).click()
            elif action == 'cancel': dialog.get_by_role('link', name='Cancel', exact=True).click()
            else: self.page.keyboard.press('Escape')
            self.expect(dialog).not_to_be_visible()
            self.expect(self.page.get_by_role('link', name='+ Add School')).to_be_focused()

    def test_outside_click_clean_closes_dirty_stays_open_and_focus_is_trapped(self):
        self.schools()
        dialog = self.open_school()
        self.page.mouse.click(5, 5)
        self.expect(dialog).not_to_be_visible()
        dialog = self.open_school()
        dialog.locator('input[name="name"]').fill('Dirty')
        self.page.mouse.click(5, 5)
        self.expect(dialog).to_be_visible()
        dialog.get_by_role('link', name='Cancel', exact=True).focus()
        self.page.keyboard.press('Tab')
        self.expect(dialog.get_by_role('button', name='Close', exact=True)).to_be_focused()
        self.page.keyboard.press('Shift+Tab')
        self.expect(dialog.get_by_role('link', name='Cancel', exact=True)).to_be_focused()

    def test_domain_guidance_and_server_errors_stay_in_modal(self):
        self.schools()
        dialog = self.open_school()
        dialog.locator('[name="name"]').fill('New School')
        dialog.locator('[name="code"]').fill('NEW')
        domains = dialog.locator('[name="domains"]')
        domains.fill('gmail.com')
        self.expect(dialog.locator('[data-domain-feedback]')).to_contain_text('must end in .edu.ph')
        dialog.get_by_role('button', name='Add School', exact=True).click()
        self.assertEqual(self.school_count('NEW'), 0)
        domains.fill('north.edu.ph')  # valid format; server catches assignment collision
        dialog.get_by_role('button', name='Add School', exact=True).click()
        self.expect(dialog.locator('.errorlist')).to_contain_text('already assigned')
        self.expect(dialog.locator('[name="name"]')).to_have_value('New School')
        self.expect(dialog).to_be_visible()
        self.assertEqual(self.school_count('NEW'), 0)

    def test_add_processing_blocks_double_submission_and_updates_table(self):
        self.schools()
        dialog = self.open_school()
        dialog.locator('[name="name"]').fill('New School')
        dialog.locator('[name="code"]').fill('NEW')
        dialog.locator('[name="domains"]').fill('new.edu.ph')
        captured = []
        self.page.route('**/systemadmin/schools/add/', lambda route: captured.append(route) if route.request.method == 'POST' else route.continue_())
        dialog.get_by_role('button', name='Add School', exact=True).click()
        self.expect(dialog.locator('button[type="submit"]')).to_be_disabled()
        self.expect(dialog.locator('.system-spinner')).to_be_visible()
        self.page.evaluate("document.querySelector('#system-form-modal form').requestSubmit()")
        self.assertEqual(len(captured), 1)
        captured[0].continue_()
        self.expect(dialog).not_to_be_visible()
        self.expect(self.page.get_by_text('New School', exact=True)).to_be_visible()
        self.expect(self.page.locator('.system-toast').first).to_contain_text('School created')
        self.assertEqual(self.school_count('NEW'), 1)

    def test_edit_school_locked_code_and_suspension_confirmation(self):
        self.schools()
        row = self.page.locator(f'tr[data-school-id="{self.school.pk}"]')
        row.get_by_role('link', name='Edit', exact=True).click()
        dialog = self.page.locator('#system-form-modal')
        self.expect(dialog.locator('[name="code"]')).to_be_disabled()
        self.expect(dialog).to_contain_text('Existing accounts keep their assigned school.')
        dialog.locator('[name="name"]').fill('North Updated')
        dialog.get_by_role('button', name='Save Changes').click()
        self.expect(dialog).not_to_be_visible()
        row.get_by_role('button', name='Suspend', exact=True).click()
        confirmation = self.page.locator('#system-confirm-modal')
        self.expect(confirmation).to_contain_text('Existing accounts and data will be retained.')
        confirmation.get_by_role('button', name='Confirm', exact=True).click()
        self.expect(row.locator('.system-pill')).to_have_text('Suspended')
        row.get_by_role('button', name='Reactivate', exact=True).click()
        self.expect(row.locator('.system-pill')).to_have_text('Active')

    def test_filter_invites_resend_and_edit_invite(self):
        self.page.goto(self.live_server_url + '/systemadmin/superadmins/')
        self.page.locator('#system-school-filter').select_option(str(self.other.pk))
        self.expect(self.page.get_by_text('alex@example.invalid', exact=True)).not_to_be_visible()
        row = self.page.locator('[data-invitation-row]')
        self.expect(row).to_be_visible()
        self.expect(row.locator('.system-pill')).to_have_text('Invited')
        row.get_by_role('button', name='Resend', exact=True).click()
        self.expect(self.page.locator('.system-toast').first).to_contain_text('Invitation email sent')
        row.get_by_role('link', name='Edit', exact=True).click()
        dialog = self.page.locator('#system-form-modal')
        self.expect(dialog.locator('[name="email"]')).to_have_value('invited@example.invalid')
        dialog.locator('[name="email"]').fill('changed@example.invalid')
        dialog.get_by_role('button', name='Send Invitation').click()
        self.expect(dialog).not_to_be_visible()
        self.expect(row).to_contain_text('changed@example.invalid')
        self.page.locator('#system-school-filter').select_option('unassigned')
        self.expect(self.page.locator('[data-filter-empty]:visible')).to_have_count(2)

    def test_different_navigation_skeletons(self):
        self.schools()
        # Cancel the default navigation at the window after the document handler
        # renders its skeleton, so browser navigation auto-waits cannot hide it.
        self.page.evaluate("window.addEventListener('click', e => e.preventDefault(), {once:true})")
        self.page.locator('.sidebar-nav').get_by_role('link', name='Manage Super Admins').click()
        self.assertTrue(self.page.evaluate("!!document.querySelector('.system-navigation-skeleton [data-skeleton=superadmins]')"))
        self.expect(self.page.locator('.sidebar-nav .active')).to_have_text('Manage Super Admins')
        self.expect(self.page.locator('.sidebar-nav [aria-current="page"]')).to_have_text('Manage Super Admins')
        self.page.goto(self.live_server_url + '/systemadmin/superadmins/')
        self.expect(self.page.locator('[data-system-directory="superadmins"]')).to_be_visible()
        self.page.evaluate("window.addEventListener('click', e => e.preventDefault(), {once:true})")
        self.page.locator('.sidebar-nav').get_by_role('link', name='Manage Schools').click()
        self.assertTrue(self.page.evaluate("!!document.querySelector('.system-navigation-skeleton [data-skeleton=schools]')"))
        self.expect(self.page.locator('.sidebar-nav .active')).to_have_text('Manage Schools')
        self.page.evaluate("window.dispatchEvent(new Event('pageshow'))")
        self.expect(self.page.locator('.sidebar-nav .active')).to_have_text('Manage Super Admins')
        self.page.goto(self.live_server_url + '/systemadmin/')
        self.expect(self.page.locator('[data-system-directory="schools"]')).to_be_visible()
        self.page.evaluate("window.addEventListener('click', e => e.preventDefault(), {once:true})")
        self.page.locator('.sidebar-nav').get_by_role('link', name='System Overview').click()
        self.expect(self.page.locator('.sidebar-nav .active')).to_have_text('System Overview')
        self.expect(self.page.locator('.system-navigation-skeleton [data-skeleton="overview"]')).to_be_visible()
        self.expect(self.page.locator('.system-navigation-skeleton .system-overview-skeleton-card')).to_have_count(3)
        self.page.goto(self.live_server_url + '/systemadmin/overview/')
        self.expect(self.page.locator('.sidebar-nav .active')).to_have_text('System Overview')

    def test_invite_and_account_edit_deactivate_reactivate(self):
        self.page.goto(self.live_server_url + '/systemadmin/superadmins/')
        self.page.get_by_role('link', name='+ Invite Super Admin').click()
        dialog = self.page.locator('#system-form-modal')
        dialog.locator('[name="email"]').fill('new-admin@example.invalid')
        dialog.locator('[name="school"]').select_option(str(self.other.pk))
        dialog.get_by_role('button', name='Send Invitation').click()
        self.expect(dialog).not_to_be_visible()
        invited = self.page.locator('[data-invitation-row]').filter(has_text='new-admin@example.invalid')
        self.expect(invited.locator('.system-pill')).to_have_text('Invited')
        invited.get_by_role('button', name='Deactivate', exact=True).click()
        self.expect(invited.locator('.system-pill')).to_have_text('Deactivated')
        invited.get_by_role('button', name='Reactivate', exact=True).click()
        self.expect(invited.locator('.system-pill')).to_have_text('Invited')
        account = self.page.locator('[data-directory-row]').filter(has_text='alex@example.invalid')
        account.get_by_role('link', name='Edit', exact=True).click()
        dialog.locator('[name="first_name"]').fill('Alex Updated')
        dialog.get_by_role('button', name='Save Changes').click()
        self.expect(dialog).not_to_be_visible()
        self.expect(account).to_contain_text('Alex Updated')
        account.get_by_role('button', name='Deactivate', exact=True).click()
        self.page.locator('#system-confirm-modal').get_by_role('button', name='Confirm', exact=True).click()
        self.expect(account.locator('.system-pill')).to_have_text('Deactivated')
        account.get_by_role('button', name='Reactivate', exact=True).click()
        self.page.locator('#system-confirm-modal').get_by_role('button', name='Confirm', exact=True).click()
        self.expect(account.locator('.system-pill')).to_have_text('Active')

    def test_mobile_layout_and_desktop_screenshot(self):
        self.schools()
        self.assertLess(self.page.locator('.system-header-action').bounding_box()['width'], 300)
        self.assertLess(self.page.locator('.main-header').bounding_box()['height'], 200)
        artifact = os.getenv('SYSTEMADMIN_SCREENSHOTS')
        if artifact:
            Path(artifact).mkdir(parents=True, exist_ok=True)
            self.page.screenshot(path=str(Path(artifact) / 'manage-schools.png'), full_page=True)
            self.page.goto(self.live_server_url + '/systemadmin/superadmins/')
            self.page.screenshot(path=str(Path(artifact) / 'manage-superadmins.png'), full_page=True)
        self.page.set_viewport_size({'width': 390, 'height': 844})
        self.schools()
        self.assertLessEqual(self.page.evaluate('document.documentElement.scrollWidth'), 390)
        dialog = self.open_school()
        self.assertLessEqual(dialog.bounding_box()['width'], 390)
