from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse

from apps.core.models import School, SchoolDomain, SuperAdminInvite, User


class ManagementUITests(TestCase):
    def setUp(self):
        self.operator = User.objects.create_user(username='ui-system-admin', role='systemadmin')
        self.school = School.objects.get(code='ADNU')
        self.admin = User.objects.create_user(username='ui-admin', first_name='Alex', last_name='Reyes',
            email='alex@example.invalid', role='superadmin', school=self.school,
            google_photo_url='https://example.invalid/avatar.jpg')
        self.client.force_login(self.operator)

    def test_no_tab_strip_on_lists_overview_or_any_form(self):
        invite = SuperAdminInvite.objects.create(email='ui-invite@example.invalid', school=self.school,
                                                invited_by=self.operator)
        routes = [('overview', []), ('manage_schools', []), ('manage_superadmins', []),
                  ('school_add', []), ('school_edit', [self.school.pk]), ('invite_add', []),
                  ('invite_edit', [invite.pk]), ('superadmin_edit', [self.admin.pk])]
        for name, args in routes:
            with self.subTest(page=name):
                response = self.client.get(reverse('systemadmin:' + name, args=args))
                self.assertEqual(response.status_code, 200)
                self.assertNotContains(response, 'class="system-tabs"')
                self.assertContains(response, 'class="sidebar-nav"')
                self.assertContains(response, 'aria-current="page"')

    def test_school_count_excludes_invites_and_other_roles_without_domain_join_duplicates(self):
        SchoolDomain(school=self.school, domain='ui-one.edu.ph').save(actor=self.operator)
        SchoolDomain(school=self.school, domain='ui-two.edu.ph').save(actor=self.operator)
        SuperAdminInvite.objects.create(email='count-invite@example.invalid', school=self.school, invited_by=self.operator)
        User.objects.create_user(username='ui-student', role='student', school=self.school)
        response = self.client.get(reverse('systemadmin:manage_schools'))
        school = next(row for row in response.context['schools'] if row.pk == self.school.pk)
        self.assertEqual(school.superadmin_count, 1)
        self.assertContains(response, 'system-domain-chip')

    def test_directory_includes_photo_invites_and_deactivated_invites_but_not_used(self):
        for label, active, used in [('pending', True, False), ('inactive', False, False), ('used', True, True)]:
            SuperAdminInvite.objects.create(email=f'{label}@example.invalid', school=self.school,
                                           invited_by=self.operator, is_active=active, used=used)
        response = self.client.get(reverse('systemadmin:manage_superadmins'))
        self.assertContains(response, 'https://example.invalid/avatar.jpg')
        self.assertContains(response, 'pending@example.invalid')
        self.assertContains(response, 'inactive@example.invalid')
        self.assertNotContains(response, 'used@example.invalid')
        self.assertContains(response, '>Invited</span>')
        self.assertContains(response, 'id="system-school-filter"')
        self.assertContains(response, 'data-directory-section', count=2)
        self.assertContains(response, 'Registered Super Admins')
        self.assertContains(response, 'Super Admin Invitations')

    def test_full_page_validation_and_school_code_lock_are_preserved(self):
        response = self.client.post(reverse('systemadmin:school_add'),
            {'name': 'New School', 'code': 'NEW', 'domains': 'gmail.com'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="system-form-content"')
        self.assertTrue(response.context['form'].errors.get('domains'))
        self.assertFalse(School.objects.filter(code='NEW').exists())
        response = self.client.get(reverse('systemadmin:school_edit', args=[self.school.pk]))
        self.assertTrue(response.context['form'].fields['code'].disabled)
        self.assertContains(response, 'Existing accounts keep their assigned school.')

    def test_full_page_invite_uses_existing_validation_and_redirect(self):
        with patch('apps.systemadmin.views.send_superadmin_invite_email', return_value=True):
            response = self.client.post(reverse('systemadmin:invite_add'),
                {'email': 'new-ui@example.invalid', 'school': self.school.pk})
        self.assertRedirects(response, reverse('systemadmin:manage_superadmins'))
        invite = SuperAdminInvite.objects.get(email='new-ui@example.invalid')
        self.assertEqual(invite.school, self.school)

    def test_empty_states(self):
        with patch('apps.systemadmin.views.School.objects') as schools:
            schools.prefetch_related.return_value.annotate.return_value = []
            response = self.client.get(reverse('systemadmin:manage_schools'))
        self.assertContains(response, 'No schools yet. Add your first school.')
        User._base_manager.filter(pk=self.admin.pk).delete()
        self.assertContains(self.client.get(reverse('systemadmin:manage_superadmins')),
                            'No Super Admins yet. Invite your first Super Admin.')

    def test_school_roles_cannot_access_lists_forms_or_actions(self):
        for role in ('student', 'faculty', 'depthead', 'superadmin'):
            user = User.objects.create_user(username='blocked-ui-' + role, role=role, school=self.school)
            self.client.force_login(user)
            for name in ('manage_schools', 'manage_superadmins', 'school_add', 'invite_add'):
                with self.subTest(role=role, page=name):
                    self.assertEqual(self.client.get(reverse('systemadmin:' + name)).status_code, 403)
            self.assertEqual(self.client.post(reverse('systemadmin:school_status', args=[self.school.pk]),
                                             {'action': 'suspend'}).status_code, 403)
        self.school.refresh_from_db()
        self.assertTrue(self.school.is_active)
