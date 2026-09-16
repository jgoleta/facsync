from allauth.core.exceptions import ImmediateHttpResponse
from allauth.socialaccount.models import SocialAccount, SocialLogin
from django.contrib.messages import get_messages
from django.contrib.messages.storage.fallback import FallbackStorage
from django.test import RequestFactory, TestCase
from django.urls import reverse

from apps.core.adapters import FacSyncSocialAdapter
from apps.core.models import DeptHeadInvite, FacultyInvite, User


class RegistrationTests(TestCase):
    def make_login(self, role=None, user=None):
        request = RequestFactory().get('/accounts/google/login/callback/')
        request.session = {} if role is None else {'registration_role': role}
        request._messages = FallbackStorage(request)
        user = user or User(email='new@example.com')
        sociallogin = SocialLogin(
            user=user,
            account=SocialAccount(
                provider='google', uid='google-registration-test',
                extra_data={'email': user.email, 'name': 'Test Faculty'},
            ),
        )
        return request, sociallogin

    def test_retired_faculty_urls_return_404_for_get_and_post(self):
        for url in (
            '/register/faculty/',
            '/register/faculty/pending/',
            '/register/faculty/pending-approval/',
        ):
            for method in ('get', 'post'):
                with self.subTest(url=url, method=method):
                    response = getattr(self.client, method)(url)
                    self.assertEqual(response.status_code, 404)

    def test_registration_page_offers_only_student_registration(self):
        response = self.client.get(reverse('core:register'))
        self.assertContains(response, reverse('core:register_student'))
        self.assertNotContains(response, '/register/faculty/')
        self.assertNotContains(response, '<h3>Faculty</h3>')

    def test_student_registration_still_starts_google_login(self):
        response = self.client.get(reverse('core:register_student'))
        self.assertRedirects(response, reverse('google_login'), fetch_redirect_response=False)
        self.assertEqual(self.client.session['registration_role'], 'student')

    def test_student_adapter_registration_remains_active(self):
        request, sociallogin = self.make_login(role='student')
        FacSyncSocialAdapter().pre_social_login(request, sociallogin)
        self.assertEqual(sociallogin.user.role, 'student')
        self.assertEqual(sociallogin.user.account_status, 'active')
        self.assertNotIn('registration_role', request.session)

    def test_stale_faculty_session_is_rejected_with_specific_message(self):
        request, sociallogin = self.make_login(role='faculty')
        request.session.update({
            'pending_faculty_email': 'new@example.com',
            'pending_faculty_name': 'Test Faculty',
            'pending_faculty_uid': 'google-registration-test',
        })
        with self.assertRaises(ImmediateHttpResponse) as caught:
            FacSyncSocialAdapter().pre_social_login(request, sociallogin)
        self.assertEqual(caught.exception.response.status_code, 302)
        self.assertEqual(caught.exception.response.url, reverse('core:register'))
        self.assertEqual([str(message) for message in get_messages(request)], [
            'Faculty self-registration is no longer available. If you were invited by a College Head or Super Admin, please check your email for an activation link, or contact them for an invite.'
        ])
        self.assertEqual(request.session, {})
        self.assertIsNone(sociallogin.user.pk)
        self.assertFalse(User.objects.exists())
        self.assertFalse(SocialAccount.objects.exists())

    def test_missing_or_invalid_registration_role_is_rejected(self):
        for role in (None, '', 'depthead', 'superadmin'):
            with self.subTest(role=role):
                request, sociallogin = self.make_login(role=role)
                with self.assertRaises(ImmediateHttpResponse) as caught:
                    FacSyncSocialAdapter().pre_social_login(request, sociallogin)
                self.assertEqual(caught.exception.response.url, reverse('core:register'))
                self.assertIsNone(sociallogin.user.pk)

    def test_unused_invites_activate_before_session_fallback(self):
        for model, role in ((FacultyInvite, 'faculty'), (DeptHeadInvite, 'depthead')):
            for session_role in (None, 'student', 'faculty'):
                with self.subTest(invite_role=role, session_role=session_role):
                    details = {'title': 'dean'} if role == 'depthead' else {}
                    invite = model.objects.create(
                        email='NEW@example.com', college='CCS', **details,
                    )
                    request, sociallogin = self.make_login(role=session_role)
                    FacSyncSocialAdapter().pre_social_login(request, sociallogin)
                    self.assertEqual(sociallogin.user.role, role)
                    self.assertEqual(sociallogin.user.account_status, 'active')
                    self.assertEqual(sociallogin.user.college, 'CCS')
                    if role == 'depthead':
                        self.assertEqual(sociallogin.user.title, 'dean')
                    self.assertFalse(model.objects.filter(pk=invite.pk).exists())
                    self.assertNotIn('registration_role', request.session)
                    self.assertEqual(list(get_messages(request)), [])

    def test_existing_pending_account_redirects_to_working_login_page(self):
        user = User.objects.create_user(
            username='pending-faculty', email='pending@example.com',
            role='faculty', account_status='pending',
        )
        request, sociallogin = self.make_login(user=user)
        with self.assertRaises(ImmediateHttpResponse) as caught:
            FacSyncSocialAdapter().pre_social_login(request, sociallogin)
        self.assertEqual(caught.exception.response.url, reverse('core:login'))
        self.assertEqual(self.client.get(caught.exception.response.url).status_code, 200)
        self.assertEqual([str(message) for message in get_messages(request)], [
            'Your registration is pending review. Please contact your College Head.'
        ])
        user.refresh_from_db()
        self.assertEqual(user.account_status, 'pending')


    def test_existing_declined_account_remains_blocked(self):
        user = User.objects.create_user(
            username='declined-faculty', email='declined@example.com',
            role='faculty', account_status='declined',
        )
        request, sociallogin = self.make_login(user=user)
        with self.assertRaises(ImmediateHttpResponse) as caught:
            FacSyncSocialAdapter().pre_social_login(request, sociallogin)
        self.assertEqual(caught.exception.response.url, reverse('core:login'))
        self.assertEqual([str(message) for message in get_messages(request)], [
            'Your registration was declined. Please contact your College Head.'
        ])
        user.refresh_from_db()
        self.assertEqual(user.account_status, 'declined')
