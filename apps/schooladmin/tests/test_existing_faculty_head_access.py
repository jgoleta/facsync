from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse

from apps.core.models import College, Department, School, User, UserRole
from apps.core.role_access import has_role
from apps.faculty.models import FacultyProfile


class ExistingFacultyHeadAccessTests(TestCase):
    def setUp(self):
        operator = User.objects.create_user(username='head-access-operator', role='systemadmin')
        self.school = School(code='HEAD', name='Head access school')
        self.school.save(actor=operator)
        self.college = College.objects.create(school=self.school, code='SCI', name='Science')
        self.department = Department.objects.create(
            school=self.school, college=self.college, code='CS', name='Computing',
            student_levels=['college'],
        )
        self.second_department = Department.objects.create(
            school=self.school, college=self.college, code='MA', name='Mathematics',
            student_levels=['college'],
        )
        self.admin = User.objects.create_user(
            username='school-admin-head-access', role='superadmin', school=self.school,
        )
        self.faculty = User.objects.create_user(
            username='existing-faculty-head', email='existing-faculty@example.com',
            role='faculty', school=self.school, department=self.department,
            college=self.college.code, profile_completed=True,
        )
        self.profile = FacultyProfile.objects.create(
            user=self.faculty, faculty_id='EXISTING-FACULTY-ID',
            college_id=self.college.code, office_location='Room 101',
        )
        self.client.force_login(self.admin)

    def payload(self, **overrides):
        data = {
            'email': self.faculty.email,
            'educational_level': 'college',
            'title': 'chairperson',
            'departments': [self.department.pk],
        }
        data.update(overrides)
        return data

    @patch('apps.schooladmin.views.send_head_role_added_email', return_value=True)
    def test_existing_faculty_receives_department_head_access_without_new_invite(self, send_email):
        response = self.client.post(
            reverse('superadmin:invite_depthead'), self.payload(),
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(response.json()['existing_account'])
        self.faculty.refresh_from_db()
        self.assertEqual(self.faculty.role, 'depthead')
        self.assertEqual(self.faculty.title, 'chairperson')
        self.assertTrue(has_role(self.faculty, 'faculty'))
        self.assertTrue(has_role(self.faculty, 'depthead'))
        self.assertEqual(list(self.faculty.managed_departments.all()), [self.department])
        self.assertEqual(self.faculty.department_id, self.department.pk)
        self.assertEqual(FacultyProfile.objects.get(user=self.faculty).pk, self.profile.pk)
        self.assertFalse(self.school.head_invites.filter(email=self.faculty.email).exists())
        send_email.assert_called_once_with(self.faculty, self.department.name, 'chairperson')
        self.client.force_login(self.faculty)
        self.assertEqual(self.client.get(reverse('depthead:college_settings')).status_code, 200)

    @patch('apps.schooladmin.views.send_head_role_added_email', return_value=True)
    def test_existing_faculty_can_become_college_head_for_all_college_departments(self, send_email):
        response = self.client.post(
            reverse('superadmin:invite_depthead'),
            self.payload(title='dean', assigned_college=self.college.pk, departments=[]),
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        self.assertEqual(response.status_code, 200, response.content)
        self.faculty.refresh_from_db()
        self.assertEqual(self.faculty.title, 'dean')
        self.assertEqual(
            set(self.faculty.managed_departments.values_list('pk', flat=True)),
            {self.department.pk, self.second_department.pk},
        )
        self.assertEqual(self.faculty.department_id, self.department.pk)
        self.assertEqual(FacultyProfile.objects.get(user=self.faculty).pk, self.profile.pk)

    @patch('apps.schooladmin.views.send_head_role_added_email', return_value=True)
    def test_removing_head_access_preserves_the_faculty_account(self, send_email):
        added = self.client.post(
            reverse('superadmin:invite_depthead'), self.payload(),
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(added.status_code, 200, added.content)

        response = self.client.post(
            reverse('superadmin:delete_depthead', args=[self.faculty.pk]),
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        self.assertEqual(response.status_code, 200, response.content)
        self.faculty.refresh_from_db()
        self.assertEqual(self.faculty.role, 'faculty')
        self.assertIsNone(self.faculty.title)
        self.assertTrue(self.faculty.is_active)
        self.assertEqual(self.faculty.account_status, 'active')
        self.assertTrue(has_role(self.faculty, 'faculty'))
        self.assertFalse(has_role(self.faculty, 'depthead'))
        self.assertFalse(self.faculty.managed_departments.exists())
        self.assertEqual(FacultyProfile.objects.get(user=self.faculty).pk, self.profile.pk)

    @patch('apps.schooladmin.views.send_head_role_added_email', return_value=True)
    def test_dual_role_head_cannot_be_deactivated_as_a_whole_account(self, send_email):
        added = self.client.post(
            reverse('superadmin:invite_depthead'), self.payload(),
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(added.status_code, 200, added.content)

        response = self.client.post(
            reverse('superadmin:remove_depthead', args=[self.faculty.pk]),
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        self.assertEqual(response.status_code, 409)
        self.faculty.refresh_from_db()
        self.assertTrue(self.faculty.is_active)
        self.assertEqual(self.faculty.account_status, 'active')
        self.assertTrue(has_role(self.faculty, 'faculty'))
        self.assertTrue(has_role(self.faculty, 'depthead'))

    def test_faculty_from_another_school_is_rejected_without_disclosure(self):
        other_school = School(code='OTHER', name='Other school')
        operator = User.objects.get(username='head-access-operator')
        other_school.save(actor=operator)
        outsider = User.objects.create_user(
            username='outside-faculty', email='outside@example.com',
            role='faculty', school=other_school,
        )

        response = self.client.post(
            reverse('superadmin:invite_depthead'),
            self.payload(email=outsider.email),
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()['error'],
            'This email is already registered or has a pending invitation.',
        )
        outsider.refresh_from_db()
        self.assertEqual(outsider.role, 'faculty')
        self.assertFalse(UserRole.objects.filter(user=outsider, role='depthead').exists())

    def test_duplicate_email_records_are_rejected_instead_of_selecting_one(self):
        duplicate_email = 'duplicate-faculty@example.com'
        first = User.objects.create_user(
            username='duplicate-faculty-one', email=duplicate_email,
            role='faculty', school=self.school, department=self.department,
            college=self.college.code,
        )
        second = User.objects.create_user(
            username='duplicate-faculty-two', email=duplicate_email.upper(),
            role='faculty', school=self.school, department=self.department,
            college=self.college.code,
        )

        response = self.client.post(
            reverse('superadmin:invite_depthead'),
            self.payload(email=duplicate_email),
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()['error'],
            'This email is already registered or has a pending invitation.',
        )
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(first.role, 'faculty')
        self.assertEqual(second.role, 'faculty')
        self.assertFalse(first.managed_departments.exists())
        self.assertFalse(second.managed_departments.exists())
