from datetime import timedelta

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase
from django.urls import reverse
from django.utils import timezone

from apps.core.models import CollegeAnnouncement, Notification, User
from apps.core.services import get_active_announcements, notify_college_users
from apps.faculty.models import FacultyProfile


class AnnouncementTests(TestCase):
    def setUp(self):
        self.head = User.objects.create_user(username='head', role='depthead', college='CCS')
        self.student = User.objects.create_user(username='student', role='student', college='CCS')
        self.faculty = User.objects.create_user(username='faculty', role='faculty', college='CCS')
        FacultyProfile.objects.create(user=self.faculty, faculty_id='ANN-1', college_id='CCS')
        self.other = User.objects.create_user(username='other', role='student', college='CON')
        self.inactive = User.objects.create_user(
            username='inactive', role='student', college='CCS', account_status='deactivated',
        )
        for audience in ('faculty', 'students', 'both'):
            self.announce(audience, audience=audience)
        self.announce('other-college', college='CON')
        self.announce('expired', expiry=timezone.now() - timedelta(seconds=1))

    def announce(self, message, **kwargs):
        defaults = {'college': 'CCS', 'posted_by': self.head, 'message': message}
        defaults.update(kwargs)
        return CollegeAnnouncement.objects.create(**defaults)

    def messages_at(self, route):
        response = self.client.get(reverse(route))
        self.assertEqual(response.status_code, 200)
        return {item['message'] for item in response.json()['announcements']}

    def test_role_endpoints_filter_audience_college_and_expiry(self):
        for user, route, expected in (
            (self.student, 'students:active_announcements', {'students', 'both'}),
            (self.faculty, 'faculty:active_announcements', {'faculty', 'both'}),
        ):
            with self.subTest(role=user.role):
                self.client.force_login(user)
                self.assertEqual(self.messages_at(route), expected)

    def test_public_endpoint_is_both_only_across_colleges_for_every_visitor(self):
        for user in (None, self.student, self.faculty):
            with self.subTest(user=user):
                self.client.logout()
                if user:
                    self.client.force_login(user)
                self.assertEqual(self.messages_at('core:active_announcements'), {'both', 'other-college'})

    def test_role_endpoints_require_correct_role(self):
        for route in ('students:active_announcements', 'faculty:active_announcements'):
            self.assertEqual(self.client.get(reverse(route)).status_code, 302)
        self.client.force_login(self.student)
        self.assertEqual(self.client.get(reverse('faculty:active_announcements')).status_code, 403)
        self.client.force_login(self.faculty)
        self.assertEqual(self.client.get(reverse('students:active_announcements')).status_code, 403)

    def test_no_college_does_not_expose_other_colleges(self):
        for college in (None, ''):
            for audience in ('faculty', 'students'):
                with self.subTest(college=college, audience=audience):
                    self.assertEqual(get_active_announcements(college, audience=audience), [])

    def test_college_matching_is_case_insensitive(self):
        self.assertEqual(
            {item['message'] for item in get_active_announcements('ccs', audience='students')},
            {'students', 'both'},
        )

    def test_student_home_ignores_newer_faculty_only_announcement(self):
        self.announce('student-visible', audience='students')
        self.announce('faculty-private', audience='faculty')
        self.client.force_login(self.student)
        response = self.client.get(reverse('students:home'))
        self.assertContains(response, 'student-visible')
        self.assertNotContains(response, 'faculty-private')

    def test_dashboard_contexts_and_popup_wiring(self):
        for user, route, endpoint, expected in (
            (self.student, 'students:dashboard', 'students:active_announcements', {'students', 'both'}),
            (self.faculty, 'faculty:dashboard', 'faculty:active_announcements', {'faculty', 'both'}),
            (None, 'core:dashboard_public', 'core:active_announcements', None),
        ):
            with self.subTest(route=route):
                self.client.logout()
                if user:
                    self.client.force_login(user)
                response = self.client.get(reverse(route))
                self.assertContains(response, 'id="announcementModal"')
                self.assertContains(response, f'data-fetch-url="{reverse(endpoint)}"')
                self.assertContains(response, 'js/announcements.js')
                if expected is not None:
                    self.assertEqual({a['message'] for a in response.context['announcements']}, expected)

    def test_creation_targets_notifications_and_returns_audience(self):
        self.client.force_login(self.head)
        for audience, recipients in (
            ('faculty', {self.faculty.pk}),
            ('students', {self.student.pk}),
            ('both', {self.faculty.pk, self.student.pk}),
        ):
            with self.subTest(audience=audience):
                message = f'created-{audience}'
                response = self.client.post(reverse('depthead:create_announcement'), {
                    'message': message, 'audience': audience,
                })
                self.assertEqual(response.status_code, 200)
                announcement = CollegeAnnouncement.objects.get(message=message)
                self.assertEqual(announcement.audience, audience)
                self.assertEqual(announcement.college, 'CCS')
                self.assertEqual(announcement.posted_by, self.head)
                self.assertGreater(announcement.expiry, timezone.now() + timedelta(days=6))
                self.assertEqual(response.json()['announcement']['audience'], audience)
                self.assertEqual(set(Notification.objects.filter(message=message).values_list('recipient_id', flat=True)), recipients)

    def test_invalid_or_missing_audience_does_not_create_or_notify(self):
        self.client.force_login(self.head)
        count = CollegeAnnouncement.objects.count()
        for audience in ('invalid', ''):
            response = self.client.post(reverse('depthead:create_announcement'), {
                'message': 'invalid', 'audience': audience,
            })
            self.assertEqual(response.status_code, 400)
        self.assertEqual(CollegeAnnouncement.objects.count(), count)
        self.assertFalse(Notification.objects.exists())

    def test_settings_lists_every_audience_and_defaults_selector_to_both(self):
        self.client.force_login(self.head)
        response = self.client.get(reverse('depthead:college_settings'))
        self.assertEqual({a.message for a in response.context['college_announcements']}, {'faculty', 'students', 'both'})
        self.assertContains(response, '<option value="both" selected>Both</option>', html=True)
        self.assertContains(response, 'id="ann-audience"')

    def test_model_default_preserves_both_visibility(self):
        announcement = self.announce('default-audience')
        announcement.refresh_from_db()
        self.assertEqual(announcement.audience, 'both')

    def test_notification_helper_default_still_includes_both_roles(self):
        notify_college_users('CCS', 'announcement', 'Test', 'default-recipients')
        self.assertEqual(set(Notification.objects.values_list('recipient_id', flat=True)), {self.student.pk, self.faculty.pk})


class AnnouncementMigrationTests(TransactionTestCase):
    def test_existing_announcements_receive_both_audience(self):
        old = [('core', '0016_alter_notification_notification_type_alter_user_role')]
        new = [('core', '0017_collegeannouncement_audience')]
        executor = MigrationExecutor(connection)
        executor.migrate(old)
        try:
            apps = executor.loader.project_state(old).apps
            user = apps.get_model('core', 'User').objects.create(username='legacy-announcement-author')
            announcement = apps.get_model('core', 'CollegeAnnouncement').objects.create(
                college='ccs', message='Existing announcement', posted_by_id=user.pk,
                expiry=timezone.now() + timedelta(days=2),
            )
            executor = MigrationExecutor(connection)
            executor.migrate(new)
            model = executor.loader.project_state(new).apps.get_model('core', 'CollegeAnnouncement')
            self.assertEqual(model.objects.get(pk=announcement.pk).audience, 'both')
        finally:
            MigrationExecutor(connection).migrate(new)
