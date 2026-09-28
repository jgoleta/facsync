from unittest.mock import MagicMock, patch

import requests
from django.core.mail import EmailMultiAlternatives
from django.test import SimpleTestCase, TestCase, override_settings

from apps.core.email_backends import BatchSendResult, BrevoEmailBackend, BrevoEmailError
from apps.core.models import CollegeAnnouncement, OfficeClosure, User
from apps.core.services import send_announcement_email_to_faculty, send_closure_email_to_faculty


@override_settings(BREVO_API_KEY='private-key', BREVO_BATCH_SIZE=2)
class PrivateBatchTests(SimpleTestCase):
    def setUp(self):
        self.session_factory = self.enterContext(patch('apps.core.email_backends.requests.Session'))
        self.post = self.session_factory.return_value.__enter__.return_value.post
        self.post.side_effect = lambda *args, **kwargs: self.response(
            {'messageIds': [f'id-{i}' for i in range(len(kwargs['json']['messageVersions']))]}
        )

    @staticmethod
    def response(data=None, status=201):
        context = MagicMock()
        response = context.__enter__.return_value
        response.status_code = status
        response.json.return_value = data
        return context

    @staticmethod
    def message(index=0):
        msg = EmailMultiAlternatives(
            'Notice', f'Hello {index}', 'FacSync <sender@example.com>', [f'user{index}@example.com'],
        )
        msg.attach_alternative(f'<p>Hello {index}</p>', 'text/html')
        return msg

    def test_private_personalized_versions_and_session_reuse(self):
        result = BrevoEmailBackend().send_personalized_batch([self.message(i) for i in range(5)])
        self.assertEqual(result, BatchSendResult(accepted=5))
        self.session_factory.assert_called_once()
        self.assertEqual(self.post.call_count, 3)
        versions = []
        for call in self.post.call_args_list:
            body = call.kwargs['json']
            for key in ('to', 'cc', 'bcc'):
                self.assertNotIn(key, body)
            self.assertFalse(call.kwargs['allow_redirects'])
            self.assertEqual(call.kwargs['timeout'], (5, 20))
            versions.extend(body['messageVersions'])
        for i, version in enumerate(versions):
            self.assertEqual(version['to'], [{'email': f'user{i}@example.com'}])
            self.assertEqual(version['textContent'], f'Hello {i}')
            self.assertEqual(version['htmlContent'], f'<p>Hello {i}</p>')
            self.assertNotIn('cc', version)
            self.assertNotIn('bcc', version)

    def test_validates_entire_batch_before_sending(self):
        for field in ('to', 'cc', 'bcc'):
            bad = self.message()
            getattr(bad, field).append('other@example.com')
            with self.subTest(field=field), self.assertRaises(BrevoEmailError):
                BrevoEmailBackend().send_personalized_batch([self.message(1), self.message(2), bad])
        self.post.assert_not_called()

    def test_empty_batch_does_not_connect(self):
        self.assertEqual(BrevoEmailBackend().send_personalized_batch([]), BatchSendResult())
        self.session_factory.assert_not_called()

    def test_rejected_chunk_does_not_resend_or_stop_later_chunk(self):
        self.post.side_effect = [self.response(status=400), self.response({'messageIds': ['last']})]
        with self.assertLogs('apps.core.email_backends'):
            result = BrevoEmailBackend().send_personalized_batch([self.message(i) for i in range(3)])
        self.assertEqual(result, BatchSendResult(accepted=1, rejected=2))
        self.assertEqual(self.post.call_count, 2)

    def test_timeout_is_unknown_sanitized_and_never_retried(self):
        self.post.side_effect = requests.Timeout('private-key and confidential response')
        with self.assertLogs('apps.core.email_backends') as logs:
            result = BrevoEmailBackend().send_personalized_batch([self.message()])
        self.assertEqual(result, BatchSendResult(unknown=1))
        self.post.assert_called_once()
        self.assertNotIn('private-key', str(logs.output))
        self.assertNotIn('confidential', str(logs.output))

    def test_ambiguous_acceptance_is_not_counted_as_success(self):
        for data in (None, {}, {'messageIds': []}, {'messageIds': ['only-one']}, {'messageIds': [None, None]}):
            with self.subTest(data=data):
                self.post.side_effect = None
                self.post.return_value = self.response(data)
                with self.assertLogs('apps.core.email_backends'):
                    result = BrevoEmailBackend().send_personalized_batch([self.message(0), self.message(1)])
                self.assertEqual(result, BatchSendResult(unknown=2))

    def test_server_failure_is_unknown(self):
        self.post.side_effect = None
        self.post.return_value = self.response(status=503)
        with self.assertLogs('apps.core.email_backends'):
            self.assertEqual(BrevoEmailBackend().send_personalized_batch([self.message()]), BatchSendResult(unknown=1))

    def test_invalid_configuration_and_sender_prevent_network(self):
        for size in (0, 1001, '100', True):
            with self.subTest(size=size), override_settings(BREVO_BATCH_SIZE=size), self.assertRaises(BrevoEmailError):
                BrevoEmailBackend().send_personalized_batch([self.message()])
        with override_settings(BREVO_API_KEY=''), self.assertRaises(BrevoEmailError):
            BrevoEmailBackend().send_personalized_batch([self.message()])
        other = self.message(1)
        other.from_email = 'other@example.com'
        with self.assertRaises(BrevoEmailError):
            BrevoEmailBackend().send_personalized_batch([self.message(), other])
        self.post.assert_not_called()


@override_settings(EMAIL_BACKEND='apps.core.email_backends.BrevoEmailBackend', BREVO_API_KEY='test')
class CollegeBatchTests(TestCase):
    def setUp(self):
        self.head = User.objects.create_user(username='head', role='depthead', college='CCS')
        for name, role, college, status, email in (
            ('one', 'faculty', 'CCS', 'active', 'one@example.com'),
            ('two', 'faculty', 'ccs', 'active', 'two@example.com'),
            ('student', 'student', 'CCS', 'active', 'student@example.com'),
            ('other', 'faculty', 'OTHER', 'active', 'other@example.com'),
            ('inactive', 'faculty', 'CCS', 'deactivated', 'inactive@example.com'),
            ('blank', 'faculty', 'CCS', 'active', '   '),
        ):
            User.objects.create_user(username=name, role=role, college=college, account_status=status, email=email)
        self.announcement = CollegeAnnouncement.objects.create(
            posted_by=self.head, college='CCS', message='Notice <private>', audience='faculty',
        )
        self.closure = OfficeClosure.objects.create(college='CCS', is_closed=True, reason='Repairs')

    @patch.object(BrevoEmailBackend, 'send_personalized_batch', return_value=BatchSendResult(accepted=2))
    def test_announcements_and_closures_preserve_audience_and_content(self, send):
        for sender, obj in ((send_announcement_email_to_faculty, self.announcement), (send_closure_email_to_faculty, self.closure)):
            sender(obj)
            messages = send.call_args.args[0]
            self.assertEqual({m.to[0] for m in messages}, {'one@example.com', 'two@example.com'})
            for message in messages:
                self.assertEqual(len(message.to), 1)
                self.assertIn(f'Hi {message.to[0].split("@")[0]}', message.body)
                self.assertTrue(message.alternatives)
        send.reset_mock()
        self.announcement.audience = 'students'
        send_announcement_email_to_faculty(self.announcement)
        self.closure.is_closed = False
        send_closure_email_to_faculty(self.closure)
        send.assert_not_called()

    @patch.object(BrevoEmailBackend, 'send_personalized_batch', side_effect=BrevoEmailError('private data'))
    @patch('apps.core.services._send_html_email')
    def test_failed_batch_never_falls_back_to_individual_sends(self, individual, batch):
        with self.assertLogs('apps.core.services') as logs:
            send_announcement_email_to_faculty(self.announcement)
        individual.assert_not_called()
        self.assertNotIn('private data', str(logs.output))
