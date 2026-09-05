from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from faculty.models import FacultyProfile


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

    def test_manage_faculty_splits_all_colleges_by_account_status(self):
        response = self.client.get(reverse('superadmin:manage_faculty'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context['pending_faculty']), [self.pending])
        self.assertEqual(list(response.context['active_faculty']), [self.active])
        self.assertTrue(response.context['active_faculty'][0].is_inactive)
        self.assertContains(response, 'data-college="CCS"')
        self.assertContains(response, 'data-college="CON"')
        self.assertContains(response, 'All Colleges')

    @patch('superadmin.views.send_faculty_approved_email')
    def test_superadmin_can_approve_pending_faculty(self, send_email):
        response = self.client.post(reverse(
            'superadmin:approve_faculty_superadmin', args=[self.pending.id]
        ))

        self.assertEqual(response.status_code, 200)
        self.pending.refresh_from_db()
        self.assertEqual(self.pending.account_status, 'active')
        send_email.assert_called_once_with(self.pending)

    def test_superadmin_can_decline_pending_faculty(self):
        response = self.client.post(reverse(
            'superadmin:decline_faculty_superadmin', args=[self.pending.id]
        ))

        self.assertEqual(response.status_code, 200)
        self.pending.refresh_from_db()
        self.assertEqual(self.pending.account_status, 'declined')

    def test_approve_rejects_non_pending_faculty(self):
        response = self.client.post(reverse(
            'superadmin:approve_faculty_superadmin', args=[self.active.id]
        ))

        self.assertEqual(response.status_code, 404)

    @patch('superadmin.views.send_faculty_removed_email')
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
