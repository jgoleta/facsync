from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.faculty.models import FacultyProfile


class ManageFacultyTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.superadmin = user_model.objects.create_user(
            username='system-admin',
            password='test-password',
            role='superadmin',
        )
        self.pending = user_model.objects.create_user(
            username='pending-faculty',
            email='pending@example.com',
            password='test-password',
            role='faculty',
            account_status='pending',
            college='CCS',
        )
        self.active = user_model.objects.create_user(
            username='active-faculty',
            email='active@example.com',
            password='test-password',
            role='faculty',
            account_status='active',
            college='CON',
            last_login=timezone.now() - timedelta(days=31),
        )
        FacultyProfile.objects.create(
            faculty_id='FAC-001',
            user=self.pending,
            college_id='CCS',
            office_location='Room 101',
        )
        FacultyProfile.objects.create(
            faculty_id='FAC-002',
            user=self.active,
            college_id='CON',
            office_location='Room 202',
        )
        self.client.force_login(self.superadmin)

    def test_manage_faculty_shows_only_active_accounts(self):
        response = self.client.get(reverse('superadmin:manage_faculty'))

        self.assertEqual(response.status_code, 200)
        self.assertNotIn('pending_faculty', response.context)
        self.assertNotContains(response, self.pending.email)
        self.assertNotContains(response, 'Pending Faculty Requests')
        self.assertNotContains(response, 'pendingFacultyCount')
        self.assertContains(response, reverse('superadmin:invite_faculty_superadmin'))
        self.assertContains(response, reverse('superadmin:remove_faculty_superadmin', args=[self.active.pk]))
        self.assertEqual(list(response.context['active_faculty']), [self.active])
        self.assertTrue(response.context['active_faculty'][0].is_inactive)
        self.assertContains(response, 'data-college="CON"')
        self.assertContains(response, 'All Colleges')

    @patch('apps.superadmin.views.send_faculty_removed_email')
    def test_superadmin_can_remove_registered_faculty(self, send_email):
        response = self.client.post(reverse(
            'superadmin:remove_faculty_superadmin', args=[self.active.id]
        ))

        self.assertEqual(response.status_code, 200)
        self.assertFalse(get_user_model().objects.filter(id=self.active.id).exists())
        send_email.assert_called_once_with('active@example.com', 'active-faculty')

    def test_non_superadmin_cannot_manage_faculty(self):
        self.client.force_login(self.active)
        response = self.client.get(reverse('superadmin:manage_faculty'))
        self.assertEqual(response.status_code, 403)


    def test_retired_approval_routes_return_404(self):
        faculty = get_user_model().objects.create_user(
            username='legacy-pending-route-test', role='faculty',
            account_status='pending', college='CCS',
        )
        for action in ('approve', 'decline'):
            for method in ('get', 'post'):
                with self.subTest(action=action, method=method):
                    response = getattr(self.client, method)(
                        f'/superadmin/faculty/{faculty.pk}/{action}/'
                    )
                    self.assertEqual(response.status_code, 404)
        faculty.refresh_from_db()
        self.assertEqual(faculty.account_status, 'pending')
