from django.test import TestCase
from django.urls import reverse

from apps.core.models import School, SuperAdminInvite, User


class SystemRemoveActionTests(TestCase):
    def setUp(self):
        self.operator = User.objects.create_user(username='platform-operator', role='systemadmin')
        self.school = School(name='Remove Test School', code='REMOVE')
        self.school.save(actor=self.operator)
        self.client.force_login(self.operator)

    def test_remove_school_suspends_and_retains_school(self):
        response = self.client.post(reverse('systemadmin:school_status', args=[self.school.pk]), {'action': 'remove'})

        self.assertRedirects(response, reverse('systemadmin:manage_school'))
        self.school.refresh_from_db()
        self.assertFalse(self.school.is_active)
        self.assertTrue(School.objects.filter(pk=self.school.pk).exists())

    def test_remove_school_admin_deactivates_and_retains_account(self):
        target = User.objects.create_user(username='admin-to-remove', role='superadmin', school=self.school)
        User.objects.create_user(username='replacement-admin', role='superadmin', school=self.school)

        response = self.client.post(reverse('systemadmin:superadmin_status', args=[target.pk]), {'action': 'remove'})

        self.assertRedirects(response, reverse('systemadmin:manage_schooladmins'))
        target.refresh_from_db()
        self.assertFalse(target.is_active)
        self.assertEqual(target.account_status, 'deactivated')
        self.assertTrue(User.objects.filter(pk=target.pk).exists())

    def test_remove_last_school_admin_is_rejected(self):
        target = User.objects.create_user(username='only-admin', role='superadmin', school=self.school)

        response = self.client.post(reverse('systemadmin:superadmin_status', args=[target.pk]), {'action': 'remove'}, follow=True)

        self.assertRedirects(response, reverse('systemadmin:manage_schooladmins'))
        target.refresh_from_db()
        self.assertTrue(target.is_active)
        self.assertContains(response, 'Keep at least one active full-access School Admin')

    def test_remove_invitation_deactivates_and_retains_invitation(self):
        invite = SuperAdminInvite.objects.create(email='remove@example.invalid', school=self.school,
            invited_by=self.operator)

        response = self.client.post(reverse('systemadmin:invite_status', args=[invite.pk]), {'action': 'remove'})

        self.assertRedirects(response, reverse('systemadmin:manage_schooladmins'))
        invite.refresh_from_db()
        self.assertFalse(invite.is_active)
        self.assertFalse(invite.used)
        self.assertTrue(SuperAdminInvite.objects.filter(pk=invite.pk).exists())

    def test_management_pages_expose_remove_actions(self):
        admin = User.objects.create_user(username='visible-admin', role='superadmin', school=self.school)
        SuperAdminInvite.objects.create(email='visible@example.invalid', school=self.school, invited_by=self.operator)

        schools = self.client.get(reverse('systemadmin:manage_school'))
        admins = self.client.get(reverse('systemadmin:manage_schooladmins'))

        self.assertContains(schools, 'value="remove"')
        self.assertContains(admins, 'Remove School Admin')
        self.assertContains(admins, 'Remove Invitation')
        self.assertContains(admins, reverse('systemadmin:superadmin_status', args=[admin.pk]))

    def test_school_admin_accounts_and_invitations_paginate_independently(self):
        for index in range(11):
            User.objects.create_user(username=f'paginated-admin-{index}', role='superadmin', school=self.school)
            SuperAdminInvite.objects.create(email=f'paginated-invite-{index}@example.invalid', school=self.school,
                invited_by=self.operator)

        response = self.client.get(reverse('systemadmin:manage_schooladmins'), {
            'accounts_page': 2, 'invitations_page': 1,
        })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['administrators'].number, 2)
        self.assertEqual(response.context['invitations'].number, 1)
        self.assertContains(response, 'accounts_page=1&amp;invitations_page=1')
        self.assertContains(response, 'invitations_page=2&amp;accounts_page=2')
