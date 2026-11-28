from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.core.models import College, Department, School, UserRole
from apps.faculty.models import FacultyProfile


class ManageFacultyActionsTests(TestCase):
    def setUp(self):
        users = get_user_model()
        operator = users.objects.create_user(username='faculty-actions-operator', role='systemadmin')
        school = School(code='FACULTYACTIONS', name='Faculty Actions School')
        school.save(actor=operator)
        college = College.objects.create(school=school, code='SCI', name='Science')
        department = Department.objects.create(
            school=school,
            college=college,
            code='BIO',
            name='Biology',
            student_levels=['college'],
        )
        self.head = users.objects.create_user(
            username='faculty-actions-head',
            password='test-password',
            role='depthead',
            title='chairperson',
            school=school,
            college=college.code,
        )
        self.head.managed_departments.add(department)

        self.faculty = users.objects.create_user(
            username='faculty-only-account',
            role='faculty',
            school=school,
            department=department,
            college=college.code,
        )
        FacultyProfile.objects.create(
            user=self.faculty,
            faculty_id='FACULTY-ONLY',
            college_id=college.code,
        )

        self.multi_role = users.objects.create_user(
            username='admin-faculty-account',
            password='admin-password',
            role='officeadmin',
            school=school,
            college='REG',
        )
        UserRole.objects.create(user=self.multi_role, role='faculty', assigned_by=self.head)
        self.multi_role.department = department
        self.multi_role.save(update_fields=['department'])
        FacultyProfile.objects.create(
            user=self.multi_role,
            faculty_id='ADMIN-FACULTY',
            college_id=college.code,
        )
        self.client.force_login(self.head)

    def test_multi_role_account_uses_reversible_faculty_access_action(self):
        response = self.client.get(reverse('depthead:admin_faculty'))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'Remove Faculty role')
        self.assertContains(response, 'Deactivate Faculty access')
        self.assertContains(response, reverse('depthead:delete_faculty', args=[self.faculty.pk]))
        self.assertNotContains(response, reverse('depthead:delete_faculty', args=[self.multi_role.pk]))

        access_url = reverse('depthead:faculty_access', args=[self.multi_role.pk])
        deactivated = self.client.post(access_url, {'action': 'deactivate'})
        self.assertEqual(deactivated.status_code, 200)
        self.assertIn('Admin login access is unchanged', deactivated.json()['message'])
        self.multi_role.refresh_from_db()
        self.assertTrue(self.multi_role.is_active)
        self.assertEqual(self.multi_role.account_status, 'active')
        self.assertFalse(UserRole.objects.get(user=self.multi_role, role='faculty').is_active)

        self.client.logout()
        self.assertTrue(self.client.login(username=self.multi_role.username, password='admin-password'))
        self.client.force_login(self.head)
        response = self.client.get(reverse('depthead:admin_faculty'))
        self.assertContains(response, 'Faculty access deactivated')
        self.assertContains(response, 'Reactivate Faculty access')

        reactivated = self.client.post(access_url, {'action': 'reactivate'})
        self.assertEqual(reactivated.status_code, 200)
        self.assertTrue(UserRole.objects.get(user=self.multi_role, role='faculty').is_active)

        retired = self.client.post(f'/depthead/adminFaculty/{self.multi_role.pk}/remove-role/')
        self.assertEqual(retired.status_code, 404)

    def test_monitoring_schedule_buttons_include_current_faculty_name(self):
        response = self.client.get(reverse('depthead:faculty_monitoring'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-faculty-name="faculty-only-account"')
        self.assertContains(response, 'data-faculty-name="admin-faculty-account"')
