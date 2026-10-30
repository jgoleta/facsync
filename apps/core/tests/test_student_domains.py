from unittest.mock import patch

from allauth.account.models import EmailAddress
from allauth.core.exceptions import ImmediateHttpResponse
from allauth.socialaccount.models import SocialAccount, SocialApp, SocialLogin
from django.contrib.messages import get_messages
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sites.models import Site
from django.test import RequestFactory, TestCase
from django.urls import reverse

from apps.core.adapters import FacSyncSocialAdapter
from apps.core.models import College, DeptHeadInvite, FacultyInvite, School, SchoolDomain, SuperAdminInvite, User
from apps.core.student_registration import EDU_ONLY, SUSPENDED, UNREGISTERED


class StudentDomainRegistrationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.actor = User.objects.create_user(username='registration-operator', role='systemadmin')
        cls.adnu = School.objects.get(code='ADNU')
        cls.unc = School(code='UNC', name='UNC student test school')
        cls.unc.save(actor=cls.actor)
        cls.adnu_domain = SchoolDomain(school=cls.adnu, domain='adnu.edu.ph')
        cls.adnu_domain.save(actor=cls.actor)
        SchoolDomain(school=cls.unc, domain='unc.edu.ph').save(actor=cls.actor)
        SchoolDomain(school=cls.unc, domain='students.unc.edu.ph').save(actor=cls.actor)
        cls.unc_college = College.objects.create(school=cls.unc, code='CCS', name='UNC-only Computer Studies')
        cls.adnu_only = College.objects.create(school=cls.adnu, code='ADNUONLY', name='ADNU-only College')
        cls.unc_admin = User.objects.create_user(username='unc-head', email='head@unc.edu.ph', role='depthead', school=cls.unc, college='CCS')
        app = SocialApp.objects.create(provider='google', name='Domain test provider', client_id='test-only', secret='test-only')
        app.sites.add(Site.objects.get_current())

    def make_login(self, email='student@unc.edu.ph', *, verified=True, provider='google', session_role='student', uid=None):
        request = RequestFactory().get('/accounts/google/login/callback/')
        request.session = {'registration_role': session_role}
        request._messages = FallbackStorage(request)
        login = SocialLogin(user=User(email=email), account=SocialAccount(provider=provider, uid=uid or email,
            extra_data={'email': email, 'email_verified': verified}),
            email_addresses=[EmailAddress(email=email, verified=verified, primary=True)])
        if provider == 'google':
            login.provider = login.account.get_provider(request)
        return request, login

    def assert_rejected(self, email, message, **options):
        request, login = self.make_login(email, **options)
        before = (User.objects.count(), SocialAccount.objects.count(), EmailAddress.objects.count())
        with self.assertRaises(ImmediateHttpResponse) as caught:
            FacSyncSocialAdapter().pre_social_login(request, login)
        self.assertEqual(caught.exception.response.url, reverse('core:register'))
        self.assertEqual([str(m) for m in get_messages(request)], [message])
        self.assertIsNone(login.user.pk)
        self.assertEqual(before, (User.objects.count(), SocialAccount.objects.count(), EmailAddress.objects.count()))

    def signup(self, email='student@unc.edu.ph'):
        request, login = self.make_login(email)
        adapter = FacSyncSocialAdapter()
        adapter.pre_social_login(request, login)
        return adapter.save_user(request, login)

    def test_verified_institutional_signup_persists_school_student_role_and_google_identity(self):
        user = self.signup()
        self.assertEqual((user.role, user.school_id, user.account_status), ('student', self.unc.pk, 'active'))
        self.assertTrue(user.is_active)
        self.assertFalse(user.is_staff or user.is_superuser or user.profile_completed or user.has_usable_password())
        self.assertIsNone(user.college)
        self.assertTrue(SocialAccount.objects.filter(user=user, provider='google').exists())
        self.assertTrue(EmailAddress.objects.filter(user=user, verified=True).exists())

    def test_case_normalization_and_multiple_explicit_domains_choose_same_school(self):
        for email in ('FIRST@UNC.EDU.PH', 'second@students.unc.edu.ph'):
            with self.subTest(email=email):
                self.assertEqual(self.signup(email).school_id, self.unc.pk)

    def test_adnu_uses_system_admin_assigned_domain(self):
        self.assertEqual(self.signup('student@adnu.edu.ph').school_id, self.adnu.pk)

    def test_non_edu_addresses_get_exact_institutional_only_message(self):
        for email in ('student@gmail.com', 'student@school.edu', 'student@edu.ph', 'student@adnu.edu.ph.evil.com'):
            with self.subTest(email=email):
                self.assert_rejected(email, EDU_ONLY)

    def test_unregistered_edu_domain_gets_exact_unregistered_message(self):
        self.assert_rejected('student@unknown.edu.ph', UNREGISTERED)

    def test_subdomain_requires_explicit_assignment_and_suffix_lookalike_does_not_match(self):
        for email in ('student@gbox.adnu.edu.ph', 'student@fakeadnu.edu.ph', 'student@unlisted.unc.edu.ph'):
            with self.subTest(email=email):
                self.assert_rejected(email, UNREGISTERED)

    def test_removed_assigned_domain_no_longer_accepts_registration(self):
        self.adnu_domain.domain = 'replacement.edu.ph'
        self.adnu_domain.save(actor=self.actor)
        self.assert_rejected('student@adnu.edu.ph', UNREGISTERED)

    def test_unverified_missing_email_and_non_google_identity_are_rejected(self):
        for email, options in [('student@unc.edu.ph', {'verified': False}), ('', {}),
                               ('student@unc.edu.ph', {'provider': 'other'})]:
            with self.subTest(email=email, options=options):
                self.assert_rejected(email, 'Please sign in with a verified Google account.', **options)

    def test_suspended_school_is_rejected_before_account_creation(self):
        self.unc.is_active = False
        self.unc.save(actor=self.actor)
        self.assert_rejected('student@unc.edu.ph', SUSPENDED)

    def test_domain_removed_during_signup_is_rechecked_at_save(self):
        request, login = self.make_login('student@adnu.edu.ph')
        adapter = FacSyncSocialAdapter()
        adapter.pre_social_login(request, login)
        self.adnu_domain.domain = 'new.adnu.edu.ph'
        self.adnu_domain.save(actor=self.actor)
        with self.assertRaises(ImmediateHttpResponse):
            adapter.save_user(request, login)
        self.assertFalse(User.objects.filter(email='student@adnu.edu.ph').exists())

    def test_school_suspended_between_callback_and_save_is_rechecked(self):
        request, login = self.make_login()
        adapter = FacSyncSocialAdapter()
        adapter.pre_social_login(request, login)
        self.unc.is_active = False
        self.unc.save(actor=self.actor)
        with self.assertRaises(ImmediateHttpResponse):
            adapter.save_user(request, login)
        self.assertFalse(User.objects.filter(email=login.user.email).exists())

    def test_domain_reassigned_during_signup_does_not_silently_change_school(self):
        request, login = self.make_login('student@adnu.edu.ph')
        adapter = FacSyncSocialAdapter()
        adapter.pre_social_login(request, login)
        self.adnu_domain.domain = 'new.adnu.edu.ph'
        self.adnu_domain.save(actor=self.actor)
        SchoolDomain(school=self.unc, domain='adnu.edu.ph').save(actor=self.actor)
        with self.assertRaises(ImmediateHttpResponse):
            adapter.save_user(request, login)
        self.assertFalse(User.objects.filter(email='student@adnu.edu.ph').exists())

    def test_delayed_signup_serialization_preserves_and_revalidates_school(self):
        request, login = self.make_login()
        adapter = FacSyncSocialAdapter()
        adapter.pre_social_login(request, login)
        restored = SocialLogin.deserialize(login.serialize())
        self.assertEqual(restored.user.school_id, self.unc.pk)
        self.assertEqual(adapter.save_user(request, restored).school_id, self.unc.pk)

    def test_forged_school_in_serialized_signup_cannot_override_domain(self):
        request, login = self.make_login()
        adapter = FacSyncSocialAdapter()
        adapter.pre_social_login(request, login)
        login.user.school = self.adnu
        with self.assertRaises(ImmediateHttpResponse):
            adapter.save_user(request, login)
        self.assertFalse(User.objects.filter(email=login.user.email).exists())

    def test_signup_form_cannot_substitute_verified_google_email(self):
        request, login = self.make_login()
        adapter = FacSyncSocialAdapter()
        adapter.pre_social_login(request, login)
        def substitute_email(req, user, form):
            user.username = 'forged-email'
            user.email = 'forged@adnu.edu.ph'
            user.save()
            return user
        with patch('allauth.account.adapter.DefaultAccountAdapter.save_user', side_effect=substitute_email):
            user = adapter.save_user(request, login, form=object())
        user.refresh_from_db()
        self.assertEqual((user.email, user.school_id), ('student@unc.edu.ph', self.unc.pk))
        self.assertFalse(User.objects.filter(email='forged@adnu.edu.ph').exists())
        self.assertTrue(SocialAccount.objects.filter(user=user, uid=login.account.uid).exists())
        self.assertTrue(EmailAddress.objects.filter(user=user, email='student@unc.edu.ph', verified=True).exists())

    def test_failed_social_account_save_rolls_back_student_creation(self):
        request, login = self.make_login()
        adapter = FacSyncSocialAdapter()
        adapter.pre_social_login(request, login)
        with patch.object(SocialAccount, 'save', side_effect=RuntimeError('failed social persistence')):
            with self.assertRaises(RuntimeError):
                adapter.save_user(request, login)
        self.assertFalse(User.objects.filter(email='student@unc.edu.ph').exists())

    def test_existing_account_is_not_recreated_or_moved_by_registration(self):
        user = self.signup()
        request, login = self.make_login(uid='different-google-id')
        adapter = FacSyncSocialAdapter()
        adapter.pre_social_login(request, login)
        with self.assertRaises(ImmediateHttpResponse):
            adapter.save_user(request, login)
        self.assertEqual(User.objects.filter(email=user.email).count(), 1)
        user.refresh_from_db()
        self.assertEqual(user.school_id, self.unc.pk)

    def test_existing_student_login_retains_school_after_domain_change(self):
        user = self.signup('student@adnu.edu.ph')
        self.adnu_domain.domain = 'new.adnu.edu.ph'
        self.adnu_domain.save(actor=self.actor)
        request, login = self.make_login(user.email)
        login.user = user
        FacSyncSocialAdapter().pre_social_login(request, login)
        user.refresh_from_db()
        self.assertEqual(user.school_id, self.adnu.pk)
        self.client.force_login(user)
        self.assertEqual(self.client.get(reverse('core:student_profile_setup')).status_code, 200)

    def test_profile_offers_own_colleges_and_rejects_foreign_college_and_forged_school(self):
        user = self.signup()
        self.client.force_login(user)
        self.assertRedirects(self.client.get(reverse('core:post_login_redirect')), reverse('core:student_profile_setup'))
        response = self.client.get(reverse('core:student_profile_setup'))
        self.assertContains(response, self.unc.name)
        self.assertContains(response, self.unc_college.name)
        self.assertNotContains(response, self.adnu_only.name)
        response = self.client.post(reverse('core:student_profile_setup'),
            {'student_id': 'STUDENT-1', 'year_level': '2', 'college': self.adnu_only.code, 'school': self.adnu.pk, 'role': 'systemadmin'})
        self.assertEqual(response.status_code, 200)
        self.assertIn('college', response.context['form'].errors)
        self.assertContains(response, 'Select a valid choice')
        user.refresh_from_db()
        self.assertFalse(user.profile_completed)
        self.assertEqual((user.school_id, user.role), (self.unc.pk, 'student'))

    def test_same_college_code_is_selected_in_student_school_and_profile_completes(self):
        user = self.signup()
        self.client.force_login(user)
        response = self.client.post(reverse('core:student_profile_setup'),
            {'student_id': 'UNC-1', 'year_level': '2', 'college': 'CCS', 'school': self.adnu.pk, 'role': 'superadmin'})
        self.assertRedirects(response, reverse('students:home'))
        user.refresh_from_db()
        self.assertEqual((user.school_id, user.role, user.college), (self.unc.pk, 'student', 'CCS'))
        self.assertTrue(user.profile_completed)

    def test_invites_still_activate_before_student_domain_rules(self):
        for model, role in [(FacultyInvite, 'faculty'), (DeptHeadInvite, 'depthead'), (SuperAdminInvite, 'superadmin')]:
            with self.subTest(role=role):
                email = role + '-invited@gmail.com'
                fields = {'college': 'CCS'} if model != SuperAdminInvite else {}
                model.objects.create(school=self.unc, email=email,
                    invited_by=self.actor if model == SuperAdminInvite else self.unc_admin, **fields)
                request, login = self.make_login(email)
                adapter = FacSyncSocialAdapter()
                adapter.pre_social_login(request, login)
                user = adapter.save_user(request, login)
                self.assertEqual((user.role, user.school_id), (role, self.unc.pk))

    def test_register_page_renders_both_exact_messages(self):
        # Use a real session-backed request so the redirect's message can be
        # rendered by the normal register page, rather than testing a literal.
        for email, expected in [('student@gmail.com', EDU_ONLY), ('student@unknown.edu.ph', UNREGISTERED)]:
            request, login = self.make_login(email)
            request.session = self.client.session
            request.session['registration_role'] = 'student'
            request._messages = FallbackStorage(request)
            with self.assertRaises(ImmediateHttpResponse):
                FacSyncSocialAdapter().pre_social_login(request, login)
            from django.http import HttpResponse
            response = HttpResponse()
            request._messages.update(response)
            request.session.save()
            # FallbackStorage normally writes the message cookie on redirect.
            for key, cookie in response.cookies.items():
                self.client.cookies[key] = cookie.value
            self.assertContains(self.client.get(reverse('core:register')), expected)
