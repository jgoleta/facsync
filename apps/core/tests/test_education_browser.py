import os
from unittest import skipUnless

from django.conf import settings
from django.urls import reverse

from apps.core.models import School, User
from apps.core.school_scope import school_scope
from apps.superadmin.tests import test_department_management_browser as fixtures


@skipUnless(os.environ.get('DEPARTMENT_BROWSER_TESTS') == '1', 'Opt-in browser checks')
class EducationBrowserTests(fixtures.DepartmentManagementBrowserTests):
    test_modal_clean_dirty_escape_focus_and_create = None
    test_server_errors_keep_values_and_pending_submission_is_locked = None
    test_head_multi_assignment_filter_and_active_sidebar = None
    test_faculty_transfer_error_filters_and_mobile_layout = None

    def setUp(self):
        super().setUp()
        def setup():
            admin = User.objects.get(username='ui-superadmin')
            with school_scope(self.school):
                self.school.set_educational_levels(['elementary', 'jhs', 'shs', 'college'], actor=admin)
            return User.objects.get(username='ui-student').pk
        self.student_id = self.database(setup)
        self.login(self.student_id)

    def login(self, user_id):
        def cookie():
            self.client.force_login(User.objects.get(pk=user_id))
            return self.client.cookies[settings.SESSION_COOKIE_NAME].value
        value = self.database(cookie)
        self.context.add_cookies([{'name': settings.SESSION_COOKIE_NAME, 'value': value, 'url': self.live_server_url}])

    def visit_profile(self):
        self.page.goto(self.live_server_url + reverse('core:student_profile_setup'))

    def test_multi_level_form_updates_grades_department_and_college_label(self):
        from playwright.sync_api import expect
        self.visit_profile()
        self.page.locator('[name=educational_level]').select_option('college')
        expect(self.page.locator('[name=year_level] option')).to_have_count(7)
        self.page.locator('[name=department]').select_option(str(self.department.pk))
        expect(self.page.locator('#student-college-label')).to_have_text('College: Browser College')
        self.page.locator('[name=educational_level]').select_option('jhs')
        expect(self.page.locator('[name=year_level] option')).to_have_count(5)
        expect(self.page.locator('#student-department-group')).to_be_hidden()
        expect(self.page.locator('[name=department]')).to_be_disabled()
        self.page.locator('[name=year_level]').select_option('8')
        self.page.locator('[name=student_id]').fill('BROWSER-008')
        self.page.get_by_role('button', name='Continue to Dashboard').click()
        self.page.wait_for_url(self.live_server_url + reverse('students:home'))
        student = self.database(lambda: User.objects.get(pk=self.student_id))
        self.assertEqual(student.educational_level, 'jhs')
        self.assertEqual(student.year_level, '8')
        self.assertIsNone(student.department_id)
        self.page.goto(self.live_server_url + reverse('students:profile'))
        expect(self.page.locator('.profile-identity')).to_contain_text('Junior High School')
        expect(self.page.locator('.profile-identity')).to_contain_text('Grade 8')

    def test_single_level_is_automatic_and_mobile_has_no_overflow(self):
        from playwright.sync_api import expect
        def single_level():
            school = School.objects.get(pk=self.school.pk)
            with school_scope(school):
                school.set_educational_levels(['shs'], actor=User.objects.get(username='ui-superadmin'))
        self.database(single_level)
        self.page.set_viewport_size({'width': 390, 'height': 844})
        self.visit_profile()
        expect(self.page.locator('[name=educational_level]')).to_have_attribute('type', 'hidden')
        expect(self.page.locator('.form-header')).to_contain_text('Browser test school')
        expect(self.page.locator('body')).to_contain_text('Senior High School is the level offered')
        expect(self.page.locator('[name=year_level] option')).to_have_count(3)
        self.assertLessEqual(self.page.evaluate('document.documentElement.scrollWidth'), 391)
        self.assertFalse(self.page_errors)

    def test_superadmin_school_settings_can_save_and_highlight_navigation(self):
        from playwright.sync_api import expect
        self.login(self.database(lambda: User.objects.get(username='ui-superadmin').pk))
        self.page.goto(self.live_server_url + reverse('superadmin:school_settings'))
        expect(self.page.locator('.sidebar-nav a[aria-current=page]')).to_have_text('School Settings')
        self.page.locator('[name=educational_levels][value=elementary]').uncheck()
        self.page.get_by_role('button', name='Save Educational Levels').click()
        self.page.wait_for_timeout(1200)
        self.assertEqual(self.database(lambda: School.objects.get(pk=self.school.pk).educational_levels), ['jhs', 'shs', 'college'])
        self.assertFalse(self.page_errors)
