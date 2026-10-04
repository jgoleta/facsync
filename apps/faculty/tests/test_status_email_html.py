from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.test import TestCase, override_settings
from django.utils import timezone

from apps.core.models import User
from apps.core.services import notify_faculty_status_subscribers
from apps.faculty.models import FacultyProfile, StatusHistory, StatusEmailDelivery
from apps.students.models import FacultyStatusSubscription
from apps.faculty.services.status_scheduler import submit_batch


@override_settings(SITE_URL='https://facsync.example', BREVO_API_KEY='test',
                   DEFAULT_FROM_EMAIL='sender@example.com', GOOGLE_CALENDAR_TIME_ZONE='Asia/Manila')
class StatusEmailHTMLTests(TestCase):
    def test_queued_template_is_saved_escaped_and_sent_with_text(self):
        owner = User.objects.create_user(username='faculty', first_name='<script>alert(1)</script>')
        student = User.objects.create_user(username='student', email='student@example.com')
        faculty = FacultyProfile.objects.create(user=owner, faculty_id='f1')
        FacultyStatusSubscription.objects.create(faculty=faculty, student=student)
        history = StatusHistory.objects.create(history_id='h1', faculty=faculty, status='busy', changed_at=timezone.now())
        notify_faculty_status_subscribers(faculty, 'busy', history=history, deferred=True)
        row = StatusEmailDelivery.objects.get()
        self.assertIn('FacSync', row.html_body)
        self.assertIn('https://facsync.example/student/view-schedule/?faculty_id=f1', row.html_body)
        self.assertIn('https://facsync.example/student/view-schedule/?faculty_id=f1', row.body)
        self.assertNotIn('<script>', row.html_body)
        self.assertIn('&lt;script&gt;', row.html_body)
        self.assertIn('Recorded at:', row.html_body)
        with patch('apps.faculty.services.status_scheduler.requests.post') as post:
            response = Mock(status_code=201)
            response.json.return_value = {'messageIds': ['id']}
            post.return_value.__enter__.return_value = response
            self.assertEqual(submit_batch([row])[0], 'accepted')
            payload = post.call_args.kwargs['json']
            version = payload['messageVersions'][0]
            self.assertEqual(version['htmlContent'], row.html_body)
            self.assertEqual(version['textContent'], row.body)
            self.assertNotIn('to', payload)

    @patch('apps.faculty.services.status_scheduler.requests.post')
    def test_legacy_pending_message_gets_branding_and_absolute_link(self, post):
        row = SimpleNamespace(subject='Original status', body='Hi <script>bad</script>\nView their schedule: /student/view-schedule/?faculty_id=f1',
                              html_body='', email='student@example.com', history=SimpleNamespace(faculty_id='f1'))
        response = Mock(status_code=201)
        response.json.return_value = {'messageIds': ['id']}
        post.return_value.__enter__.return_value = response
        self.assertEqual(submit_batch([row])[0], 'accepted')
        version = post.call_args.kwargs['json']['messageVersions'][0]
        self.assertIn('FacSync', version['htmlContent'])
        self.assertNotIn('<script>', version['htmlContent'])
        self.assertIn('https://facsync.example/student/view-schedule/?faculty_id=f1', version['textContent'])
