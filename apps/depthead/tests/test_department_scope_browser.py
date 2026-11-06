"""Opt-in browser verification using only a disposable local server."""
import os
from unittest import skipUnless

from django.conf import settings
from django.urls import reverse

from apps.superadmin.tests import test_department_management_browser as browser_fixtures
from apps.core.models import User


@skipUnless(os.environ.get('DEPARTMENT_BROWSER_TESTS') == '1', 'Opt-in browser checks')
class DepartmentScopeBrowserTests(browser_fixtures.DepartmentManagementBrowserTests):
    # The inherited fixture supplies the local server/browser, not duplicate tests.
    test_modal_clean_dirty_escape_focus_and_create = None
    test_server_errors_keep_values_and_pending_submission_is_locked = None
    test_head_multi_assignment_filter_and_active_sidebar = None
    test_faculty_transfer_error_filters_and_mobile_layout = None

    def setUp(self):
        super().setUp()
        def login():
            user = User.objects.get(pk=self.head.pk)
            user.managed_departments.add(self.second)
            self.client.force_login(user)
            return self.client.cookies[settings.SESSION_COOKIE_NAME].value
        cookie = self.database(login)
        self.context.add_cookies([{'name': settings.SESSION_COOKIE_NAME, 'value': cookie, 'url': self.live_server_url}])
        self.context.route('**/api/ai-insights/**', lambda route: route.fulfill(json={'available': False}))

    def test_combined_overview_and_faculty_invitation_form(self):
        from playwright.sync_api import expect
        self.page.goto(self.live_server_url + reverse('depthead:admin_dashboard'))
        expect(self.page.get_by_role('heading', name='Department Overview', exact=True)).to_be_visible()
        expect(self.page.locator('.overview-hero')).to_contain_text(self.second.name)
        self.page.goto(self.live_server_url + reverse('depthead:admin_faculty'))
        expect(self.page.locator('body')).to_contain_text('ui-faculty')
        # Department selection belongs to the invite action; reporting has no filter.
        self.page.locator('#addFacultyBtn').click()
        expect(self.page.locator('#facultyForm select[name=department]')).to_have_count(1)
        expect(self.page.locator('#facultyForm select[name=department] option')).to_have_count(3)
        self.assertFalse(self.page_errors)

    def test_settings_show_separate_action_targets_and_save_description(self):
        from playwright.sync_api import expect
        self.page.goto(self.live_server_url + reverse('depthead:college_settings'))
        expect(self.page.get_by_role('heading', name=self.department.name, exact=True)).to_be_visible()
        expect(self.page.get_by_role('heading', name=self.second.name, exact=True)).to_be_visible()
        form = self.page.locator('form').filter(has=self.page.locator(f'textarea#description-{self.second.pk}'))
        form.locator('textarea').fill('Updated through department settings')
        form.get_by_role('button', name='Save Description', exact=True).click()
        expect(self.page.locator(f'#description-{self.second.pk}')).to_have_value('Updated through department settings')
        self.page.wait_for_timeout(1200)
        self.assertEqual(self.database(lambda: self.second.__class__.objects.get(pk=self.second.pk).description), 'Updated through department settings')
        self.assertEqual(self.database(lambda: self.department.__class__.objects.get(pk=self.department.pk).description), '')
        self.assertFalse(self.page_errors)
