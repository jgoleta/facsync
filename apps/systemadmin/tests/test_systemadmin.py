from io import StringIO
from unittest.mock import patch

from allauth.account.models import EmailAddress
from allauth.core.exceptions import ImmediateHttpResponse
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from allauth.socialaccount.models import SocialAccount, SocialLogin, SocialApp
from django.contrib.sites.models import Site
from django.core import mail
from django.contrib.messages.storage.fallback import FallbackStorage
from django.core.exceptions import PermissionDenied
from django.core.management import call_command, CommandError
from django.test import RequestFactory, TestCase
from django.urls import reverse

from apps.core.adapters import FacSyncSocialAdapter
from apps.core.models import College, DeptHeadInvite, School, SchoolChangeLog, SchoolDomain, SuperAdminInvite, User
from apps.core.school_scope import school_scope


class SystemAdminTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.operator = User.objects.create_user(username='operator', email='operator@gmail.com',
            role='systemadmin', is_staff=True, is_superuser=True)
        app = SocialApp.objects.create(provider='google', name='Local test provider', client_id='test-only', secret='test-only')
        app.sites.add(Site.objects.get_current())
        cls.adnu = School.objects.get(code='ADNU')
        cls.unc = School(code='UNC', name='UNC Test School')
        cls.unc.save(actor=cls.operator)
        SchoolDomain(school=cls.unc, domain='unc.edu.ph').save(actor=cls.operator)
        cls.admin = User.objects.create_user(username='adnu-admin', email='adnu-admin@gmail.com',
            role='superadmin', school=cls.adnu)
        cls.replacement = User.objects.create_user(username='adnu-replacement', email='replacement@gmail.com',
            role='superadmin', school=cls.adnu)
        cls.unc_admin = User.objects.create_user(username='unc-admin', email='unc-admin@gmail.com',
            role='superadmin', school=cls.unc)
        cls.invite = SuperAdminInvite.objects.create(school=cls.unc, email='invited@gmail.com', invited_by=cls.operator)

    def setUp(self):
        self.client.force_login(self.operator)

    def make_login(self, email='invited@gmail.com', verified=True, uid='invited-google'):
        request = RequestFactory().get('/accounts/google/login/callback/')
        request.session = {'registration_role': 'student'}
        request._messages = FallbackStorage(request)
        login = SocialLogin(user=User(email=email), account=SocialAccount(provider='google', uid=uid,
            extra_data={'email': email, 'email_verified': verified}),
            email_addresses=[EmailAddress(email=email, verified=verified, primary=True)])
        login.provider = login.account.get_provider(request)
        return request, login

    def test_both_tabs_render_all_schools_accounts_and_pending_invites(self):
        self.assertContains(self.client.get(reverse('systemadmin:manage_schools')), 'UNC Test School')
        response = self.client.get(reverse('systemadmin:manage_superadmins'))
        for email in (self.admin.email, self.unc_admin.email, self.invite.email):
            self.assertContains(response, email)
        for route in ('school_add', 'invite_add'):
            self.assertEqual(self.client.get(reverse('systemadmin:' + route)).status_code, 200)
        for route, pk in [('school_edit', self.unc.pk), ('superadmin_edit', self.admin.pk), ('invite_edit', self.invite.pk)]:
            self.assertEqual(self.client.get(reverse('systemadmin:' + route, args=[pk])).status_code, 200)

    def test_only_schoolless_active_systemadmin_can_enter_every_endpoint(self):
        routes = [('manage_schools', []), ('manage_superadmins', []), ('school_add', []), ('invite_add', []),
            ('school_edit', [self.unc.pk]), ('school_status', [self.unc.pk]), ('invite_edit', [self.invite.pk]),
            ('invite_status', [self.invite.pk]), ('invite_resend', [self.invite.pk]),
            ('superadmin_edit', [self.admin.pk]), ('superadmin_status', [self.admin.pk])]
        for role in ('student', 'faculty', 'depthead', 'superadmin'):
            user = User.objects.create_user(username='denied-' + role, role=role, school=self.adnu)
            self.client.force_login(user)
            for route, args in routes:
                with self.subTest(role=role, route=route):
                    url = reverse('systemadmin:' + route, args=args)
                    self.assertEqual(self.client.get(url).status_code, 403)
                    self.assertEqual(self.client.post(url, {}).status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.get(reverse('systemadmin:manage_schools')).status_code, 302)

    def test_create_school_requires_domains_normalizes_and_logs_actor(self):
        response = self.client.post(reverse('systemadmin:school_add'), {
            'name': ' Test Institution ', 'code': 'test', 'domains': 'TEST.EDU.PH\nstudents.test.edu.ph'})
        self.assertRedirects(response, reverse('systemadmin:manage_schools'))
        school = School.objects.get(code='TEST')
        self.assertEqual(school.name, 'Test Institution')
        self.assertSetEqual(set(school.domains.values_list('domain', flat=True)), {'test.edu.ph', 'students.test.edu.ph'})
        self.assertTrue(school.is_active)
        self.assertTrue(school.changes.exists())
        self.assertEqual(set(school.changes.values_list('actor_id', flat=True)), {self.operator.pk})

    def test_invalid_duplicate_and_empty_domains_do_not_create_partial_school(self):
        for domains in ('gmail.com', 'edu.ph', 'https://new.edu.ph', '*.new.edu.ph', 'unc.edu.ph',
                        'new.edu.ph\nNEW.edu.ph', ''):
            with self.subTest(domains=domains):
                response = self.client.post(reverse('systemadmin:school_add'), {'name': 'Bad', 'code': 'BAD', 'domains': domains})
                self.assertEqual(response.status_code, 200)
                self.assertFalse(School.objects.filter(code='BAD').exists())

    def test_edit_name_and_replace_last_domain_keeps_code_locked_and_audit(self):
        response = self.client.post(reverse('systemadmin:school_edit', args=[self.unc.pk]), {
            'name': 'Renamed School', 'code': 'FORGED', 'domains': 'new.unc.edu.ph'})
        self.assertEqual(response.status_code, 302)
        self.unc.refresh_from_db()
        self.assertEqual(self.unc.code, 'UNC')
        self.assertEqual(self.unc.name, 'Renamed School')
        self.assertEqual(list(self.unc.domains.values_list('domain', flat=True)), ['new.unc.edu.ph'])
        change = self.unc.changes.filter(field='name').first()
        self.assertEqual((change.old_value, change.new_value, change.actor_id), ('UNC Test School', 'Renamed School', self.operator.pk))
        self.assertTrue(self.unc.changes.filter(field='domains').exists())
        self.assertContains(self.client.get(reverse('systemadmin:school_edit', args=[self.unc.pk])), 'Recent changes')

    def test_suspension_and_reactivation_preserve_records_and_block_existing_session(self):
        self.assertEqual(self.client.get(reverse('systemadmin:school_status', args=[self.unc.pk])).status_code, 405)
        self.client.post(reverse('systemadmin:school_status', args=[self.unc.pk]), {'action': 'suspend'})
        self.unc.refresh_from_db()
        self.assertFalse(self.unc.is_active)
        self.client.force_login(self.unc_admin)
        self.assertEqual(self.client.get(reverse('superadmin:manage_students')).status_code, 403)
        self.client.force_login(self.operator)
        self.client.post(reverse('systemadmin:school_status', args=[self.unc.pk]), {'action': 'reactivate'})
        self.unc.refresh_from_db()
        self.assertTrue(self.unc.is_active)
        self.assertTrue(User.objects.filter(pk=self.unc_admin.pk).exists())
        self.assertEqual(self.unc.domains.count(), 1)

    def test_invite_any_email_domain_delivers_school_specific_email_and_rejects_collisions(self):
        response = self.client.post(reverse('systemadmin:invite_add'), {'email': 'NEW@GMAIL.COM', 'school': self.adnu.pk})
        self.assertEqual(response.status_code, 302)
        invite = SuperAdminInvite.objects.get(email='new@gmail.com')
        self.assertEqual((invite.school_id, invite.invited_by_id), (self.adnu.pk, self.operator.pk))
        self.assertEqual(mail.outbox[-1].to, ['new@gmail.com'])
        self.assertIn(self.adnu.name, mail.outbox[-1].body)
        self.assertIn('/login/', mail.outbox[-1].body)
        DeptHeadInvite.objects.create(email='head@gmail.com', school=self.adnu, college='CCS')
        for email in (self.admin.email, 'NEW@gmail.com', 'head@gmail.com'):
            response = self.client.post(reverse('systemadmin:invite_add'), {'email': email, 'school': self.unc.pk})
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, 'already registered or has a pending invitation')

    def test_pending_invite_edit_deactivate_reactivate_and_resend(self):
        self.client.post(reverse('systemadmin:invite_edit', args=[self.invite.pk]),
            {'email': 'changed@gmail.com', 'school': self.adnu.pk})
        self.invite.refresh_from_db()
        self.assertEqual((self.invite.email, self.invite.school_id), ('changed@gmail.com', self.adnu.pk))
        self.client.post(reverse('systemadmin:invite_status', args=[self.invite.pk]), {'action': 'deactivate'})
        self.invite.refresh_from_db()
        self.assertFalse(self.invite.is_active)
        self.assertEqual(self.client.post(reverse('systemadmin:invite_resend', args=[self.invite.pk])).status_code, 404)
        self.client.post(reverse('systemadmin:invite_status', args=[self.invite.pk]), {'action': 'reactivate'})
        self.client.post(reverse('systemadmin:invite_resend', args=[self.invite.pk]))
        self.assertEqual(len(mail.outbox), 2)

    @patch('apps.systemadmin.views._send_html_email', side_effect=RuntimeError('delivery failed'))
    def test_delivery_failure_keeps_retryable_invite(self, send):
        response = self.client.post(reverse('systemadmin:invite_add'), {'email': 'retry@gmail.com', 'school': self.adnu.pk}, follow=True)
        self.assertContains(response, 'could not be sent')
        self.assertTrue(SuperAdminInvite.objects.filter(email='retry@gmail.com', used=False).exists())

    def test_activation_requires_verified_google_and_uses_invited_school_without_domain_rule(self):
        request, login = self.make_login(email='INVITED@gmail.com')
        adapter = FacSyncSocialAdapter()
        adapter.pre_social_login(request, login)
        self.assertEqual((login.user.role, login.user.school_id), ('superadmin', self.unc.pk))
        self.assertNotIn('registration_role', request.session)
        # Exercise real allauth persistence and Google association, not just role assignment.
        user = adapter.save_user(request, login)
        self.invite.refresh_from_db()
        self.assertTrue(self.invite.used)
        self.assertTrue(user.profile_completed)
        self.assertIsNone(user.college)
        self.assertTrue(SocialAccount.objects.filter(user=user, provider='google').exists())
        self.client.force_login(user)
        self.assertRedirects(self.client.get(reverse('core:post_login_redirect')), reverse('superadmin:superadmin_dashboard'))
        self.assertEqual(self.client.get(reverse('systemadmin:manage_schools')).status_code, 403)

    def test_unverified_google_cancelled_invite_and_suspended_school_cannot_activate(self):
        request, login = self.make_login(verified=False)
        with self.assertRaises(ImmediateHttpResponse):
            FacSyncSocialAdapter().pre_social_login(request, login)
        self.invite.is_active = False
        self.invite.save()
        request, login = self.make_login()
        with self.assertRaises(ImmediateHttpResponse):
            FacSyncSocialAdapter().pre_social_login(request, login)
        self.invite.is_active = True
        self.invite.save()
        self.unc.is_active = False
        self.unc.save(actor=self.operator)
        with self.assertRaises(ImmediateHttpResponse):
            FacSyncSocialAdapter().pre_social_login(request, login)
        self.assertFalse(User.objects.filter(email=self.invite.email).exists())

    def test_failed_activation_retains_invite_and_signup_round_trip_rechecks_server_state(self):
        adapter = FacSyncSocialAdapter()
        request, login = self.make_login()
        adapter.pre_social_login(request, login)
        with patch.object(DefaultSocialAccountAdapter, 'save_user', side_effect=RuntimeError('failed save')):
            with self.assertRaises(RuntimeError):
                adapter.save_user(request, login)
        self.invite.refresh_from_db()
        self.assertFalse(self.invite.used)
        del login._facsync_invite
        self.invite.is_active = False
        self.invite.save()
        with self.assertRaises(ImmediateHttpResponse):
            adapter.save_user(request, login)
        self.assertFalse(User.objects.filter(email=self.invite.email).exists())

    def test_school_account_cannot_create_superadmin_invite_or_use_faculty_invite_collision(self):
        with school_scope(self.adnu):
            with self.assertRaises(PermissionDenied):
                SuperAdminInvite.objects.create(school=self.adnu, invited_by=self.admin, email='forged@gmail.com')
        self.client.force_login(self.admin)
        response = self.client.post(reverse('superadmin:invite_faculty_superadmin'), {'email': self.invite.email, 'college': 'CCS'},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(response.status_code, 400)

    def test_account_edit_does_not_change_school_email_or_role_and_status_preserves_last_admin(self):
        self.client.post(reverse('systemadmin:superadmin_edit', args=[self.admin.pk]), {
            'first_name': 'Updated', 'last_name': 'Name', 'school': self.unc.pk, 'role': 'systemadmin', 'email': 'forged@gmail.com'})
        self.admin.refresh_from_db()
        self.assertEqual((self.admin.first_name, self.admin.school_id, self.admin.role, self.admin.email),
                         ('Updated', self.adnu.pk, 'superadmin', 'adnu-admin@gmail.com'))
        self.client.post(reverse('systemadmin:superadmin_status', args=[self.admin.pk]), {'action': 'deactivate'})
        self.admin.refresh_from_db()
        self.assertFalse(self.admin.is_active)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse('superadmin:manage_students')).status_code, 302)
        self.client.force_login(self.operator)
        response = self.client.post(reverse('systemadmin:superadmin_status', args=[self.replacement.pk]), {'action': 'deactivate'}, follow=True)
        self.assertContains(response, 'Keep at least one active Super Admin')
        self.replacement.refresh_from_db()
        self.assertTrue(self.replacement.is_active)
        self.client.post(reverse('systemadmin:superadmin_status', args=[self.admin.pk]), {'action': 'reactivate'})
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_active)

    def test_state_changes_require_post_and_csrf(self):
        from django.test import Client
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.operator)
        self.assertEqual(client.post(reverse('systemadmin:school_status', args=[self.unc.pk]), {'action': 'suspend'}).status_code, 403)
        for route, pk in [('school_status', self.unc.pk), ('invite_status', self.invite.pk),
                          ('invite_resend', self.invite.pk), ('superadmin_status', self.admin.pk)]:
            self.assertEqual(self.client.get(reverse('systemadmin:' + route, args=[pk])).status_code, 405)

    def test_systemadmin_redirect_bypasses_profile_setup_and_suspended_school(self):
        self.operator.profile_completed = False
        self.operator.save()
        self.assertRedirects(self.client.get(reverse('core:post_login_redirect')), reverse('systemadmin:manage_schools'))

    def test_bootstrap_command_preview_conversion_preserves_google_link_and_replacement(self):
        account = SocialAccount.objects.create(user=self.admin, provider='google', uid='existing-google')
        output = StringIO()
        call_command('create_systemadmin', email=self.admin.email, convert_existing=True, stdout=output)
        self.admin.refresh_from_db()
        self.assertEqual(self.admin.role, 'superadmin')
        call_command('create_systemadmin', email=self.admin.email, convert_existing=True, apply=True, stdout=StringIO())
        self.admin.refresh_from_db()
        self.assertEqual((self.admin.role, self.admin.school_id, self.admin.college), ('systemadmin', None, None))
        account.refresh_from_db()
        self.assertEqual(account.user_id, self.admin.pk)
        self.assertTrue(User.objects.filter(pk=self.replacement.pk, role='superadmin', school=self.adnu).exists())
        self.assertFalse(self.admin.is_superuser)
        with self.assertRaises(CommandError):
            call_command('create_systemadmin', email=self.unc_admin.email, convert_existing=True, apply=True, stdout=StringIO())

    def test_bootstrap_new_account_requires_apply_and_verified_google_first_login(self):
        call_command('create_systemadmin', email='bootstrap@gmail.com', stdout=StringIO())
        self.assertFalse(User.objects.filter(email='bootstrap@gmail.com').exists())
        call_command('create_systemadmin', email='bootstrap@gmail.com', apply=True, stdout=StringIO())
        user = User.objects.get(email='bootstrap@gmail.com')
        self.assertFalse(user.has_usable_password())
        self.assertIsNone(user.school_id)
        request, login = self.make_login(email=user.email, verified=False, uid='bootstrap-google')
        with self.assertRaises(ImmediateHttpResponse):
            FacSyncSocialAdapter().pre_social_login(request, login)
        request, login = self.make_login(email=user.email, uid='bootstrap-google')
        FacSyncSocialAdapter().pre_social_login(request, login)
        self.assertEqual(login.user.pk, user.pk)
        self.assertEqual(SocialAccount.objects.get(user=user).uid, 'bootstrap-google')
        # A later different Google identity cannot attach by email again.
        request, login = self.make_login(email=user.email, uid='different-google')
        with self.assertRaises(ImmediateHttpResponse):
            FacSyncSocialAdapter().pre_social_login(request, login)

    def test_bootstrap_rejects_ambiguous_identity_and_arbitrary_role_conversion(self):
        User.objects.create_user(username='duplicate', email=self.admin.email.upper(), role='student', school=self.adnu)
        with self.assertRaises(CommandError):
            call_command('create_systemadmin', email=self.admin.email, convert_existing=True, apply=True, stdout=StringIO())
        with self.assertRaises(CommandError):
            call_command('create_systemadmin', email=self.unc_admin.email, apply=True, stdout=StringIO())
        student = User.objects.create_user(username='student-conversion', email='student@gmail.com', school=self.adnu)
        with self.assertRaises(CommandError):
            call_command('create_systemadmin', email=student.email, convert_existing=True, apply=True, stdout=StringIO())

    def test_django_admin_role_conversion_clears_school_and_guards_last_superadmin(self):
        from apps.core.admin import SystemAwareUserChangeForm
        def payload(user):
            return dict(username=user.username, email=user.email, role='systemadmin',
                school=user.school_id, account_status='active', is_active=True,
                date_joined=user.date_joined.isoformat())
        form = SystemAwareUserChangeForm(data=payload(self.admin), instance=self.admin)
        self.assertTrue(form.is_valid(), form.errors)
        user = form.save()
        self.assertEqual((user.role, user.school_id, user.college), ('systemadmin', None, None))
        form = SystemAwareUserChangeForm(data=payload(self.unc_admin), instance=self.unc_admin)
        self.assertFalse(form.is_valid())
        self.assertIn('Keep at least one active Super Admin', str(form.errors))

    def test_school_suspended_between_prelogin_and_save_prevents_activation(self):
        request, login = self.make_login()
        adapter = FacSyncSocialAdapter()
        adapter.pre_social_login(request, login)
        self.unc.is_active = False
        self.unc.save(actor=self.operator)
        with self.assertRaises(ImmediateHttpResponse):
            adapter.save_user(request, login)
        self.invite.refresh_from_db()
        self.assertFalse(self.invite.used)
        self.assertFalse(User.objects.filter(email=self.invite.email).exists())

    def test_restored_signup_session_activates_only_from_live_server_invite(self):
        request, login = self.make_login()
        adapter = FacSyncSocialAdapter()
        adapter.pre_social_login(request, login)
        restored = SocialLogin.deserialize(login.serialize())
        self.assertFalse(hasattr(restored, '_facsync_invite'))
        user = adapter.save_user(request, restored)
        self.assertEqual((user.role, user.school_id), ('superadmin', self.unc.pk))
        self.invite.refresh_from_db()
        self.assertTrue(self.invite.used)
