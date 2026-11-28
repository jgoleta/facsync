from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.core.models import College, Department, School, UserRole
from apps.faculty.models import FacultyProfile


class SchoolAdminDualRoleFacultyAccessTests(TestCase):
    def setUp(self):
        users = get_user_model()
        operator = users.objects.create_user(username='dual-role-operator', role='systemadmin')
        self.school = School(code='DUALROLE', name='Dual Role School')
        self.school.save(actor=operator)
        college = College.objects.create(school=self.school, code='SCI', name='Science')
        department = Department.objects.create(
            school=self.school,
            college=college,
            code='BIO',
            name='Biology',
            student_levels=['college'],
        )
        self.school_admin = users.objects.create_user(
            username='dual-role-school-admin',
            password='school-admin-password',
            role='superadmin',
            school=self.school,
        )
        self.dual_role = users.objects.create_user(
            username='dual-role-office-admin',
            password='dual-role-password',
            role='officeadmin',
            school=self.school,
            college='REG',
        )
        UserRole.objects.create(
            user=self.dual_role,
            role='faculty',
            assigned_by=self.school_admin,
        )
        self.dual_role.department = department
        self.dual_role.save(update_fields=['department'])
        FacultyProfile.objects.create(
            user=self.dual_role,
            faculty_id='DUAL-ROLE-FACULTY',
            college_id=college.code,
        )
        self.faculty_only = users.objects.create_user(
            username='faculty-only-for-admin',
            role='faculty',
            school=self.school,
            college=college.code,
            department=department,
        )
        FacultyProfile.objects.create(
            user=self.faculty_only,
            faculty_id='FACULTY-ONLY-ADMIN',
            college_id=college.code,
        )
        self.client.force_login(self.school_admin)

    def test_dual_role_actions_are_limited_to_faculty_access(self):
        response = self.client.get(reverse('superadmin:manage_faculty'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Deactivate Faculty access')
        self.assertContains(response, reverse(
            'superadmin:faculty_access_superadmin', args=[self.dual_role.pk]))
        self.assertNotContains(response, reverse(
            'superadmin:delete_faculty_superadmin', args=[self.dual_role.pk]))
        self.assertContains(response, reverse(
            'superadmin:delete_faculty_superadmin', args=[self.faculty_only.pk]))

        admin_page = self.client.get(reverse('superadmin:manage_admins'))
        self.assertContains(admin_page, reverse(
            'superadmin:delete_office_admin', args=[self.dual_role.pk]))

    def test_deactivating_faculty_access_preserves_admin_login_and_is_reversible(self):
        url = reverse('superadmin:faculty_access_superadmin', args=[self.dual_role.pk])
        response = self.client.post(url, {'action': 'deactivate'})

        self.assertEqual(response.status_code, 200)
        self.assertIn('Admin login access is unchanged', response.json()['message'])
        self.dual_role.refresh_from_db()
        self.assertTrue(self.dual_role.is_active)
        self.assertEqual(self.dual_role.account_status, 'active')
        self.assertFalse(UserRole.objects.get(user=self.dual_role, role='faculty').is_active)

        self.client.logout()
        self.assertTrue(self.client.login(
            username=self.dual_role.username,
            password='dual-role-password',
        ))
        self.client.force_login(self.school_admin)
        page = self.client.get(reverse('superadmin:manage_faculty'))
        self.assertContains(page, 'Faculty access deactivated')
        self.assertContains(page, 'Reactivate Faculty access')

        reactivated = self.client.post(url, {'action': 'reactivate'})
        self.assertEqual(reactivated.status_code, 200)
        self.assertTrue(UserRole.objects.get(user=self.dual_role, role='faculty').is_active)

    def test_whole_account_faculty_actions_reject_dual_role_user(self):
        deactivate = self.client.post(
            reverse('superadmin:remove_faculty_superadmin', args=[self.dual_role.pk]),
        )
        delete = self.client.post(
            reverse('superadmin:delete_faculty_superadmin', args=[self.dual_role.pk]),
        )

        self.assertEqual(deactivate.status_code, 409)
        self.assertEqual(delete.status_code, 409)
        self.dual_role.refresh_from_db()
        self.assertTrue(self.dual_role.is_active)
        self.assertTrue(UserRole.objects.get(user=self.dual_role, role='faculty').is_active)
