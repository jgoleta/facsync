from unittest.mock import patch
from django.test import TestCase
from django.core import mail
from apps.core.models import User, CollegeAnnouncement, OfficeClosure
from apps.core.services import send_announcement_email_to_faculty, send_closure_email_to_faculty


class EmailDeliveryTests(TestCase):
    def setUp(self):
        self.head = User.objects.create_user(username='head', role='depthead', college='ccs')
        for name, role, college, status, email in (
            ('one', 'faculty', 'CCS', 'active', 'one@example.com'),
            ('two', 'faculty', 'ccs', 'active', 'two@example.com'),
            ('student', 'student', 'ccs', 'active', 'student@example.com'),
            ('other', 'faculty', 'con', 'active', 'other@example.com'),
            ('inactive', 'faculty', 'ccs', 'deactivated', 'inactive@example.com'),
            ('blank', 'faculty', 'ccs', 'active', ''),
        ):
            User.objects.create_user(username=name, role=role, college=college, account_status=status, email=email)
        self.announcement = CollegeAnnouncement.objects.create(college='ccs', posted_by=self.head, message='Important notice')
        self.closure = OfficeClosure.objects.create(college='ccs', is_closed=True, reason='Repairs')

    def test_announcement_audience_and_multipart_content(self):
        for audience, expected in [('students', 0), ('faculty', 2), ('both', 2)]:
            with self.subTest(audience=audience):
                mail.outbox.clear()
                self.announcement.audience = audience
                send_announcement_email_to_faculty(self.announcement)
                self.assertEqual(len(mail.outbox), expected)
                for message in mail.outbox:
                    self.assertEqual(len(message.to), 1)
                    self.assertIn(message.to[0], ['one@example.com', 'two@example.com'])
                    self.assertIn('Important notice', message.body)
                    self.assertEqual(message.alternatives[0].mimetype, 'text/html')
                    self.assertIn('College of Computer Studies', message.body)

    def test_closure_email_and_open_guard(self):
        send_closure_email_to_faculty(self.closure)
        self.assertEqual(len(mail.outbox), 2)
        self.assertIn('Repairs', mail.outbox[0].body)
        self.assertEqual(mail.outbox[0].alternatives[0].mimetype, 'text/html')
        self.closure.is_closed = False
        send_closure_email_to_faculty(self.closure)
        self.assertEqual(len(mail.outbox), 2)

    def test_recipient_failure_does_not_stop_remaining_sends(self):
        for sender, obj in [(send_announcement_email_to_faculty, self.announcement), (send_closure_email_to_faculty, self.closure)]:
            with patch('apps.core.services._send_html_email', side_effect=[RuntimeError('SMTP failed'), None]) as send:
                with self.assertLogs('apps.core.services', level='ERROR'):
                    sender(obj)
                self.assertEqual(send.call_count, 2)
