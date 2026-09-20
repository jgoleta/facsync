from datetime import date
from smtplib import SMTPException
from unittest.mock import patch

from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.core.models import User
from apps.faculty.models import FacultyProfile, ScheduleEvent


@override_settings(SITE_URL='https://facsync.example/', EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class ScheduleUploadEmailTests(TestCase):
    def setUp(self):
        self.head = User.objects.create(username='head-email', role='depthead', college='CCS')
        self.user = User.objects.create(username='faculty-email', role='faculty', college='CCS', email='faculty@example.com')
        self.faculty = FacultyProfile.objects.create(faculty_id='email-faculty', user=self.user, college_id='CCS')
        self.client.force_login(self.head)
        self.url = reverse('depthead:upload_faculty_schedule', args=[self.faculty.pk])

    def upload(self, url=None, row=None):
        header = 'OFFERING_ID,SUBJ_CODE,SECTION,SUBJECT_TITLE,UNITS,LECTURE,LAB,DAYFROM,DAYTO,TIMEFROM,TIMETO,ROOM\n'
        row = row or 'OFF-1,CS101,BSCS-1A,Computing,3,2,1,2026-09-21,2026-09-21,08:00,09:30,Room 204\n'
        return self.client.post(url or self.url, {'file': SimpleUploadedFile('schedule.csv', (header+row).encode(), content_type='text/csv')})

    def test_success_single_date_batch_only_summary_and_link(self):
        ScheduleEvent.objects.create(faculty=self.faculty, title='OLD EVENT', date=date(2026, 9, 1))
        response = self.upload()
        self.assertEqual(response.status_code, 201)
        self.assertIs(response.json()['email_sent'], True)
        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertEqual(email.to, ['faculty@example.com'])
        html = email.alternatives[0].content
        for text in ('head-email', 'CS101', 'BSCS-1A', 'Computing', 'OFF-1', 'Room 204',
                     '08:00', '09:30', 'Units: 3', 'Lecture: 2', 'Lab: 1',
                     'only the entries from this upload', 'https://facsync.example/faculty/schedule/'):
            self.assertIn(text, html)
        self.assertEqual(html.count('Sep 21, 2026'), 1)
        self.assertIn('1 schedule entry', html)
        self.assertNotIn('OLD EVENT', html)
        self.assertIn('Computing', email.body)
        self.assertEqual(self.faculty.schedule_events.count(), 2)

    def test_date_range_and_escaped_content(self):
        response = self.upload(row='OFF-1,CS101,A,<script>bad</script>,3,2,1,2026-09-21,2026-12-18,08:00,09:30,<b>Room</b>\n')
        self.assertEqual(response.status_code, 201)
        html = mail.outbox[0].alternatives[0].content
        self.assertIn('Sep 21, 2026 &ndash; Dec 18, 2026', html)
        self.assertIn('&lt;script&gt;bad&lt;/script&gt;', html)
        self.assertNotIn('<script>', html)
        self.assertIn('&lt;b&gt;Room&lt;/b&gt;', html)

    @patch('apps.core.services.EmailMultiAlternatives.send', side_effect=SMTPException('mail unavailable'))
    def test_email_failure_preserves_successful_upload(self, send):
        with self.assertLogs('apps.depthead.views', level='ERROR'):
            response = self.upload()
        self.assertEqual(response.status_code, 201)
        self.assertIs(response.json()['email_sent'], False)
        self.assertEqual(response.json()['added_count'], 1)
        self.assertEqual(self.faculty.schedule_events.count(), 1)
        self.faculty.refresh_from_db()
        self.assertIsNotNone(self.faculty.schedule_last_updated_at)

    def test_missing_recipient_does_not_attempt_send(self):
        self.user.email = ' '
        self.user.save(update_fields=['email'])
        with patch('apps.core.services._send_html_email') as send:
            response = self.upload()
        self.assertEqual(response.status_code, 201)
        self.assertIs(response.json()['email_sent'], False)
        send.assert_not_called()

    @patch('apps.core.services.EmailMultiAlternatives.send', return_value=0)
    def test_backend_zero_sends_is_not_reported_as_sent(self, send):
        self.assertIs(self.upload().json()['email_sent'], False)

    def test_invalid_and_cross_college_uploads_send_nothing(self):
        self.assertEqual(self.upload(row='invalid\n').status_code, 400)
        self.faculty.college_id = 'CBA'
        self.faculty.save(update_fields=['college_id'])
        self.assertEqual(self.upload().status_code, 404)
        self.assertEqual(len(mail.outbox), 0)
        self.assertFalse(self.faculty.schedule_events.exists())

    def test_repeated_uploads_send_once_each_and_self_upload_sends_nothing(self):
        for _ in range(2):
            self.assertEqual(self.upload().status_code, 201)
        self.assertEqual(len(mail.outbox), 2)
        for email in mail.outbox:
            self.assertIn('1 schedule entry', email.alternatives[0].content)
        self.client.force_login(self.user)
        response = self.upload(reverse('faculty:upload_schedule'))
        self.assertEqual(response.status_code, 201)
        self.assertEqual(len(mail.outbox), 2)
        self.assertEqual(self.faculty.schedule_events.count(), 3)
