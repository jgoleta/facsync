from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.core.models import College, Department, DeptHeadInvite, Office, OfficeAdminInvite, School


class AdminInvitationRemovalTests(TestCase):
    def setUp(self):
        users = get_user_model()
        operator = users.objects.create_user(username='admin-invite-operator', role='systemadmin')
        self.school = School(code='ADMININVITE', name='Admin Invitation School')
        self.school.save(actor=operator)
        self.admin = users.objects.create_user(
            username='admin-invite-school-admin',
            password='test-password',
            role='superadmin',
            school=self.school,
        )
        college = College.objects.create(school=self.school, code='SCI', name='Science')
        self.department = Department.objects.create(
            school=self.school,
            college=college,
            code='BIO',
            name='Biology',
            student_levels=['college'],
        )
        Office.objects.create(school=self.school, code='REG', name='Registrar')
        self.head_invite = DeptHeadInvite.objects.create(
            school=self.school,
            email='pending-head@example.com',
            college=college.code,
            title='chairperson',
            invited_by=self.admin,
        )
        self.head_invite.departments.add(self.department)
        self.office_invite = OfficeAdminInvite.objects.create(
            school=self.school,
            email='pending-office@example.com',
            office='REG',
            invited_by=self.admin,
        )
        self.client.force_login(self.admin)

    def removal_url(self, invite_type, invite):
        return reverse('superadmin:remove_admin_invite', args=[invite_type, invite.pk])

    def test_invitation_table_only_shows_remove_action(self):
        response = self.client.get(reverse('superadmin:manage_admins'))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'Edit and email')
        self.assertContains(response, 'Resend', count=2)
        self.assertContains(response, 'Remove invitation', count=2)
        self.assertContains(response, self.removal_url('head', self.head_invite))
        self.assertContains(response, self.removal_url('office', self.office_invite))
        self.assertContains(response, reverse('superadmin:resend_head_invite', args=[self.head_invite.pk]))
        self.assertContains(response, reverse('superadmin:resend_office_admin_invite', args=[self.office_invite.pk]))

    def test_pending_head_invitation_can_be_removed(self):
        response = self.client.post(self.removal_url('head', self.head_invite))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'success': True, 'message': 'Invitation removed.'})
        self.assertFalse(DeptHeadInvite.objects.filter(pk=self.head_invite.pk).exists())
        self.assertTrue(OfficeAdminInvite.objects.filter(pk=self.office_invite.pk).exists())

    def test_pending_office_invitation_can_be_removed(self):
        response = self.client.post(self.removal_url('office', self.office_invite))

        self.assertEqual(response.status_code, 200)
        self.assertFalse(OfficeAdminInvite.objects.filter(pk=self.office_invite.pk).exists())

    def test_removal_requires_post(self):
        response = self.client.get(self.removal_url('head', self.head_invite))

        self.assertEqual(response.status_code, 405)
        self.assertTrue(DeptHeadInvite.objects.filter(pk=self.head_invite.pk).exists())

    @patch('apps.schooladmin.views.send_depthead_invite_email', return_value=True)
    def test_pending_head_invitation_can_be_resent(self, send_email):
        response = self.client.post(
            reverse('superadmin:resend_head_invite', args=[self.head_invite.pk]),
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['message'], 'Invitation emailed.')
        self.assertTrue(DeptHeadInvite.objects.filter(pk=self.head_invite.pk).exists())
        send_email.assert_called_once_with(
            self.head_invite.email,
            'Biology',
            'chairperson',
            False,
            '',
        )

    @patch('apps.schooladmin.views.send_office_admin_invite_email', return_value=True)
    def test_pending_office_invitation_can_be_resent(self, send_email):
        response = self.client.post(
            reverse('superadmin:resend_office_admin_invite', args=[self.office_invite.pk]),
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['message'], 'Invitation emailed.')
        self.assertTrue(OfficeAdminInvite.objects.filter(pk=self.office_invite.pk).exists())
        send_email.assert_called_once_with(self.office_invite.email, 'REG')

    @patch('apps.schooladmin.views.send_depthead_invite_email', return_value=False)
    def test_failed_head_resend_preserves_invitation_and_reports_warning(self, send_email):
        response = self.client.post(
            reverse('superadmin:resend_head_invite', args=[self.head_invite.pk]),
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()['email_sent'])
        self.assertIn('could not be sent', response.json()['message'])
        self.assertTrue(DeptHeadInvite.objects.filter(pk=self.head_invite.pk).exists())
        send_email.assert_called_once()

    @patch('apps.schooladmin.views.send_depthead_invite_email')
    def test_head_resend_rejects_inactive_department(self, send_email):
        self.department.is_active = False
        self.department.save(update_fields=['is_active'])

        response = self.client.post(
            reverse('superadmin:resend_head_invite', args=[self.head_invite.pk]),
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()['success'])
        send_email.assert_not_called()

    @patch('apps.schooladmin.views.send_depthead_invite_email')
    def test_consumed_head_invitation_cannot_be_resent(self, send_email):
        self.head_invite.used = True
        self.head_invite.save(update_fields=['used'])

        response = self.client.post(
            reverse('superadmin:resend_head_invite', args=[self.head_invite.pk]),
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        self.assertEqual(response.status_code, 404)
        send_email.assert_not_called()

    @patch('apps.schooladmin.views.send_depthead_invite_email', return_value=True)
    def test_limited_admin_requires_admin_management_permission(self, send_email):
        self.admin.school_admin_full_access = False
        self.admin.school_admin_permissions = []
        self.admin.save(update_fields=['school_admin_full_access', 'school_admin_permissions'])
        url = reverse('superadmin:resend_head_invite', args=[self.head_invite.pk])

        denied = self.client.post(url, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(denied.status_code, 403)
        send_email.assert_not_called()

        self.admin.school_admin_permissions = ['admins']
        self.admin.save(update_fields=['school_admin_permissions'])
        allowed = self.client.post(url, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(allowed.status_code, 200)
        send_email.assert_called_once()
