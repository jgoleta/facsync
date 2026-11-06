"""Opt-in real-browser checks; DEPARTMENT_BROWSER_TESTS=1 requires Playwright."""
import os
from concurrent.futures import ThreadPoolExecutor
from unittest import skipUnless

from django.conf import settings
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.urls import reverse

from apps.core.models import College, Department, School, User
from apps.faculty.models import ConsultationRequest, FacultyProfile


@skipUnless(os.environ.get('DEPARTMENT_BROWSER_TESTS') == '1', 'Opt-in browser checks')
class DepartmentManagementBrowserTests(StaticLiveServerTestCase):
    def setUp(self):
        super().setUp()
        operator = User.objects.create_user(username='ui-operator', role='systemadmin')
        self.school = School(code='UITEST', name='Browser test school')
        self.school.save(actor=operator)
        college = College.objects.create(school=self.school, code='UI', name='Browser College')
        self.department = Department.objects.create(school=self.school, college=college, code='DUI', name='Department of Browser Computing')
        self.second = Department.objects.create(school=self.school, code='DSECOND', name='Department of Browser Mathematics')
        admin = User.objects.create_user(username='ui-superadmin', role='superadmin', school=self.school)
        self.head = User.objects.create_user(username='ui-head', role='depthead', title='dean', school=self.school)
        self.head.managed_departments.add(self.department)
        faculty = User.objects.create_user(username='ui-faculty', role='faculty', school=self.school, department=self.department, college='UI')
        self.profile = FacultyProfile.objects.create(user=faculty, faculty_id='ui-faculty', college_id='UI')
        student = User.objects.create_user(username='ui-student', role='student', school=self.school)
        ConsultationRequest.objects.create(request_id='ui-history', user=student, faculty=self.profile,
            department=self.department, date='2026-11-10', status='completed')
        self.client.force_login(admin)
        cookie = self.client.cookies[settings.SESSION_COOKIE_NAME].value
        from playwright.sync_api import sync_playwright
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch()
        self.context = self.browser.new_context(viewport={'width': 1360, 'height': 900})
        self.context.route('**/*', lambda route: route.continue_() if route.request.url.startswith(self.live_server_url) else route.abort())
        self.context.add_cookies([{'name': settings.SESSION_COOKIE_NAME, 'value': cookie, 'url': self.live_server_url}])
        self.page = self.context.new_page()
        self.page_errors = []
        self.page.on('pageerror', lambda error: self.page_errors.append(str(error)))

    def tearDown(self):
        try:
            self.browser.close()
            self.playwright.stop()
        finally:
            super().tearDown()

    def visit(self, name):
        self.page.goto(self.live_server_url + reverse('superadmin:' + name))

    def database(self, callback):
        # Playwright owns a running event loop; ORM assertions run outside it.
        with ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(callback).result()

    def test_modal_clean_dirty_escape_focus_and_create(self):
        from playwright.sync_api import expect
        self.visit('manage_departments')
        trigger = self.page.get_by_role('button', name='Add Department', exact=True)
        trigger.click()
        dialog = self.page.locator('#departmentModal')
        expect(dialog).to_be_visible()
        expect(dialog.locator('[name=name]')).to_be_focused()
        self.page.mouse.click(5, 5)
        expect(dialog).not_to_be_visible()
        expect(trigger).to_be_focused()
        trigger.click(); dialog.locator('[name=name]').fill('Typed name')
        self.page.mouse.click(5, 5)
        expect(dialog).to_be_visible()
        self.page.keyboard.press('Escape')
        expect(dialog).not_to_be_visible()
        trigger.click()
        dialog.locator('[name=name]').fill('Department of New Browser Studies')
        dialog.locator('[name=code]').fill('DNEW')
        dialog.get_by_role('button', name='Save Department').click()
        expect(self.page.locator('table')).to_contain_text('Department of New Browser Studies')
        self.assertTrue(self.database(lambda: Department.objects.filter(school_id=self.school.pk, code='DNEW').exists()))
        self.assertFalse(self.page_errors)

    def test_server_errors_keep_values_and_pending_submission_is_locked(self):
        from playwright.sync_api import expect
        self.visit('manage_departments')
        self.page.get_by_role('button', name='Add Department', exact=True).click()
        dialog = self.page.locator('#departmentModal')
        dialog.locator('[name=name]').fill('Department of Duplicate Studies')
        dialog.locator('[name=code]').fill('DUP')
        self.page.evaluate('''() => {
            window.savedFetch = window.fetch; window.postCount = 0;
            window.fetch = (...args) => { window.postCount += 1; return new Promise(resolve => window.finishSave = resolve); };
        }''')
        submit = dialog.get_by_role('button', name='Save Department')
        submit.click()
        expect(submit).to_be_disabled()
        expect(dialog.locator('#managementLoading')).to_have_class('loading-overlay show')
        self.page.evaluate('document.querySelector("#departmentModal form").requestSubmit()')
        self.assertEqual(self.page.evaluate('window.postCount'), 1)
        self.page.evaluate('window.finishSave({ok:false,json:async()=>({success:false,error:"This code is already in use."})})')
        expect(dialog.locator('[data-form-error]')).to_have_text('This code is already in use.')
        expect(dialog.locator('[name=name]')).to_have_value('Department of Duplicate Studies')
        expect(submit).to_be_enabled()
        dialog.get_by_role('button', name='Cancel', exact=True).click()
        expect(dialog).not_to_be_visible()

    def test_head_multi_assignment_filter_and_active_sidebar(self):
        from playwright.sync_api import expect
        self.visit('manage_admins')
        expect(self.page.locator('.sidebar-nav a[aria-current=page]')).to_have_text('Manage Admins')
        self.page.get_by_role('button', name='Edit assignments', exact=True).click()
        dialog = self.page.locator('#headEditModal')
        dialog.locator('[name=departments]').select_option([str(self.department.pk), str(self.second.pk)])
        dialog.get_by_role('button', name='Save Assignments').click()
        expect(self.page.locator('table').first).to_contain_text(self.second.name)
        self.assertEqual(self.database(lambda: User.objects.get(pk=self.head.pk).managed_departments.count()), 2)
        self.page.locator('#headDepartmentFilter').select_option(str(self.second.pk))
        expect(self.page.locator('table').first.locator('[data-department-ids]')).to_be_visible()

    def test_faculty_transfer_error_filters_and_mobile_layout(self):
        from playwright.sync_api import expect
        self.visit('manage_faculty')
        self.page.get_by_role('button', name='Edit assignment', exact=True).click()
        dialog = self.page.locator('#facultyAssignmentModal')
        dialog.locator('[name=unit]').select_option('department:' + str(self.second.pk))
        dialog.get_by_role('button', name='Save Assignment', exact=True).click()
        expect(dialog.locator('[data-form-error]')).to_contain_text('activity records')
        expect(dialog.locator('[name=unit]')).to_have_value('department:' + str(self.second.pk))
        dialog.get_by_role('button', name='Cancel', exact=True).click()
        self.page.locator('#facultyUnitFilter').select_option('department:' + str(self.second.pk))
        expect(self.page.locator('[data-faculty-empty]')).to_be_visible()
        self.page.set_viewport_size({'width': 390, 'height': 844})
        self.assertLessEqual(self.page.evaluate('document.documentElement.scrollWidth'), 391)
        self.assertEqual(self.database(lambda: FacultyProfile.objects.get(pk=self.profile.pk).user.department_id), self.department.pk)
