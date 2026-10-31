from django.test import TestCase
from django.urls import reverse

from apps.core.models import School, SuperAdminInvite, User


class SystemOverviewTests(TestCase):
    def setUp(self):
        self.operator = User.objects.create_user(username='platform-operator', role='systemadmin')
        self.adnu = School.objects.get(code='ADNU')
        self.other = School(name='Other School', code='OTHER')
        self.other.save(actor=self.operator)
        self.suspended = School(name='Suspended School', code='SUSPENDED', is_active=False)
        self.suspended.save(actor=self.operator)
        self.url = reverse('systemadmin:overview')

    def test_platform_counts_include_all_schools_but_only_actionable_invitations(self):
        for index, school in enumerate((self.adnu, self.other, self.suspended)):
            User.objects.create_user(username=f'school-admin-{index}', role='superadmin', school=school,
                                     account_status='deactivated' if index == 2 else 'active', is_active=index != 2)
        User.objects.create_user(username='not-an-admin', role='student', school=self.other)
        for label, school, active, used in (
            ('adnu', self.adnu, True, False), ('other', self.other, True, False),
            ('cancelled', self.other, False, False), ('consumed', self.other, True, True),
            ('suspended', self.suspended, True, False),
        ):
            SuperAdminInvite.objects.create(email=f'{label}@example.invalid', school=school,
                                           invited_by=self.operator, is_active=active, used=used)
        self.client.force_login(self.operator)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        for key, expected in {'total_schools': 3, 'active_schools': 2, 'suspended_schools': 1,
                              'total_superadmins': 3, 'pending_invitations': 2}.items():
            self.assertEqual(response.context[key], expected)
        self.assertContains(response, 'System Overview')
        self.assertContains(response, 'Pending invitations')
        self.assertIn('no-store', response['Cache-Control'])

    def test_overview_has_no_administrators_or_invitations_when_none_created(self):
        self.client.force_login(self.operator)
        response = self.client.get(self.url)
        self.assertEqual(response.context['total_superadmins'], 0)
        self.assertEqual(response.context['pending_invitations'], 0)
        self.assertContains(response, reverse('systemadmin:manage_schools'))
        self.assertContains(response, reverse('systemadmin:manage_superadmins'))

    def test_school_roles_cannot_access_platform_totals(self):
        for role in ('student', 'faculty', 'depthead', 'superadmin'):
            with self.subTest(role=role):
                user = User.objects.create_user(username=f'blocked-{role}', role=role, school=self.adnu)
                self.client.force_login(user)
                self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_anonymous_user_must_log_in(self):
        self.assertEqual(self.client.get(self.url).status_code, 302)

    def test_school_assigned_systemadmin_cannot_access_overview(self):
        # Forged DB state must not grant platform scope.
        self.client.force_login(self.operator)
        User._base_manager.filter(pk=self.operator.pk).update(school=self.adnu)
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_superadmin_pages_show_school_overview_and_shared_logo(self):
        user = User.objects.create_user(username='local-admin', role='superadmin', school=self.adnu)
        self.client.force_login(user)
        for name in ('superadmin_dashboard', 'manage_colleges', 'manage_admins', 'manage_faculty', 'manage_students'):
            with self.subTest(page=name):
                response = self.client.get(reverse('superadmin:' + name))
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, 'School Overview')
                self.assertNotContains(response, 'System Overview')
                self.assertContains(response, 'https://i.imgur.com/MFtx6rV.png')
                self.assertNotContains(response, '<span class="brand-mark">S</span>')

    def test_systemadmin_pages_share_logo_and_overview_navigation(self):
        self.client.force_login(self.operator)
        for name in ('overview', 'manage_schools', 'manage_superadmins'):
            with self.subTest(page=name):
                response = self.client.get(reverse('systemadmin:' + name))
                self.assertContains(response, self.url)
                self.assertContains(response, 'https://i.imgur.com/MFtx6rV.png')
                self.assertNotContains(response, '<span class="brand-mark">S</span>')
