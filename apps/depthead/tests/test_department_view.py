from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.core.models import College, Department, School


class CollegeHeadDepartmentViewTests(TestCase):
    def setUp(self):
        users = get_user_model()
        operator = users.objects.create_user(username='department-view-operator', role='systemadmin')
        self.school = School(code='DEPTVIEW', name='Department View School')
        self.school.save(actor=operator)

        self.college = College.objects.create(school=self.school, code='SCI', name='Science')
        other_college = College.objects.create(school=self.school, code='ART', name='Arts')
        self.first = Department.objects.create(
            school=self.school, college=self.college, code='BIO', name='Biology',
            student_levels=['college'],
        )
        self.second = Department.objects.create(
            school=self.school, college=self.college, code='CHEM', name='Chemistry',
            student_levels=['college'],
        )
        self.outside = Department.objects.create(
            school=self.school, college=other_college, code='HIST', name='History',
            student_levels=['college'],
        )
        self.head = users.objects.create_user(
            username='science-college-head',
            password='test-password',
            role='depthead',
            title='dean',
            school=self.school,
            college=self.college.code,
        )
        self.client.force_login(self.head)
        self.url = reverse('depthead:select_department_view')

    def test_selector_only_lists_departments_in_heads_college(self):
        dashboard = self.client.get(reverse('depthead:admin_dashboard'))
        response = self.client.get(reverse('depthead:college_settings'))

        self.assertNotContains(dashboard, 'Department view')
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'depthead/departmentSettings.html')
        self.assertContains(response, 'Department view')
        self.assertContains(response, self.first.name)
        self.assertContains(response, self.second.name)
        self.assertNotContains(response, self.outside.name)
        self.assertNotContains(response, 'All departments')
        self.assertNotContains(response, 'id="details-department"')
        self.assertNotContains(response, 'id="availability-department"')
        self.assertNotContains(response, 'id="announcement-department"')
        self.assertEqual(response.content.count(b'name="department_id"'), 1)

    def test_selected_department_limits_managed_scope(self):
        response = self.client.post(self.url, {
            'department_id': self.first.pk,
            'next': reverse('depthead:admin_dashboard'),
        })

        self.assertRedirects(response, reverse('depthead:admin_dashboard'))
        self.assertEqual(
            self.client.session[f'department_view:{self.head.pk}'],
            self.first.pk,
        )
        dashboard = self.client.get(reverse('depthead:admin_dashboard'))
        self.assertEqual(dashboard.wsgi_request.managed_scope.department_ids, (self.first.pk,))

    def test_department_outside_college_cannot_be_selected(self):
        response = self.client.post(self.url, {'department_id': self.outside.pk})

        self.assertEqual(response.status_code, 404)
        self.assertEqual(self.client.session[f'department_view:{self.head.pk}'], self.first.pk)

    def test_first_department_is_selected_by_default(self):
        response = self.client.get(reverse('depthead:admin_dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.session[f'department_view:{self.head.pk}'], self.first.pk)
        self.assertEqual(response.wsgi_request.managed_scope.department_ids, (self.first.pk,))

    def test_details_form_uses_selected_department_without_its_own_dropdown(self):
        self.client.post(self.url, {'department_id': self.second.pk})

        response = self.client.post(
            reverse('depthead:edit_college_description'),
            {'description': 'Selected department description'},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['success'])
        self.first.refresh_from_db()
        self.second.refresh_from_db()
        self.assertEqual(self.first.description, '')
        self.assertEqual(self.second.description, 'Selected department description')
