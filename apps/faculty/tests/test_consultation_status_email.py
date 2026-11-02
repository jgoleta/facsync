from datetime import date, time
from types import SimpleNamespace
from unittest.mock import patch

from django.core import mail
from django.test import SimpleTestCase, override_settings

from apps.faculty.views import _notify_consultation_student


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
                   SITE_URL='https://facsync.example')
class ConsultationStatusEmailTests(SimpleTestCase):
    def consultation(self, status):
        student = SimpleNamespace(email='student@example.invalid', username='student',
                                  get_full_name=lambda: '<Student>')
        teacher = SimpleNamespace(username='faculty', get_full_name=lambda: 'Faculty & Co')
        return SimpleNamespace(user=student, faculty=SimpleNamespace(user=teacher), status=status,
                               faculty_note='<script>alert(1)</script>', date=date(2026, 11, 9),
                               start_time=time(10), end_time=time(11),
                               get_agenda_display=lambda: 'Grade Consultation',
                               get_consultation_type_display=lambda: 'Online')

    def test_decline_and_cancel_use_branded_html_with_original_plain_text(self):
        for status in ('declined', 'cancelled'):
            with self.subTest(status=status):
                subject = f'FacSync consultation {status}'
                body = f'Your consultation was {status}.'
                _notify_consultation_student(self.consultation(status), subject, body)
                message = mail.outbox[-1]
                self.assertEqual(message.to, ['student@example.invalid'])
                self.assertEqual(message.subject, subject)
                self.assertEqual(message.body, body)
                html = message.alternatives[0].content
                self.assertIn(f'Consultation {status}', html)
                self.assertIn('FacSync', html)
                self.assertIn('&lt;Student&gt;', html)
                self.assertIn('&lt;script&gt;', html)
                self.assertNotIn('<script>', html)
                self.assertIn('Grade Consultation', html)
                self.assertIn('View consultation', html)
                self.assertIn('https://facsync.example/student/consultation-requests/', html)
                self.assertEqual(html.count('<a '), 1)
        self.assertEqual(len(mail.outbox), 2)

    def test_missing_email_sends_nothing(self):
        item = self.consultation('cancelled')
        item.user.email = ''
        _notify_consultation_student(item, 'Cancelled', 'Cancelled')
        self.assertEqual(len(mail.outbox), 0)

    def test_email_error_does_not_escape_status_notification(self):
        with patch('apps.faculty.views._send_html_email', side_effect=RuntimeError('private-secret')), \
                self.assertLogs('apps.faculty.views', level='WARNING') as logs:
            _notify_consultation_student(self.consultation('declined'), 'Declined', 'Declined')
        self.assertNotIn('private-secret', str(logs.output))
