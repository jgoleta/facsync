import os
import subprocess
import sys
from unittest.mock import MagicMock, patch

import requests
from django.core.mail import EmailMessage, EmailMultiAlternatives, get_connection
from django.test import SimpleTestCase, override_settings

from apps.core.email_backends import BrevoEmailBackend, BrevoEmailError
from apps.core.services import send_faculty_invite_email, send_faculty_removed_email


@override_settings(
    EMAIL_BACKEND='apps.core.email_backends.BrevoEmailBackend',
    BREVO_API_KEY='test-api-key',
    DEFAULT_FROM_EMAIL='FacSync <sender@example.com>',
    SITE_URL='https://facsync.example',
)
class BrevoBackendTests(SimpleTestCase):
    def setUp(self):
        self.post = self.enterContext(patch('apps.core.email_backends.requests.post'))
        self.response = self.post.return_value.__enter__.return_value
        self.response.status_code = 201
        self.response.json.return_value = {'messageId': 'test-message-id'}

    def message(self):
        return EmailMessage('Subject', 'Plain text', to=['recipient@example.com'])

    def test_django_interface_preserves_multipart_and_address_fields(self):
        message = EmailMultiAlternatives(
            'Subject', 'Plain text', 'FacSync <sender@example.com>',
            ['Recipient <recipient@example.com>'],
            cc=['copy@example.com'], bcc=['hidden@example.com'],
            reply_to=['Reply <reply@example.com>'],
        )
        message.attach_alternative('<p>HTML</p>', 'text/html')
        self.assertEqual(message.send(), 1)
        args, kwargs = self.post.call_args
        self.assertEqual(args, ('https://api.brevo.com/v3/smtp/email',))
        self.assertEqual(kwargs['headers']['api-key'], 'test-api-key')
        self.assertEqual(kwargs['timeout'], (5, 20))
        self.assertFalse(kwargs['allow_redirects'])
        self.assertEqual(kwargs['json'], {
            'sender': {'email': 'sender@example.com', 'name': 'FacSync'},
            'subject': 'Subject', 'textContent': 'Plain text', 'htmlContent': '<p>HTML</p>',
            'to': [{'email': 'recipient@example.com', 'name': 'Recipient'}],
            'cc': [{'email': 'copy@example.com'}],
            'bcc': [{'email': 'hidden@example.com'}],
            'replyTo': {'email': 'reply@example.com', 'name': 'Reply'},
        })

    def test_existing_invite_and_removal_helpers_use_backend_unchanged(self):
        send_faculty_invite_email('recipient@example.com', 'CCS')
        send_faculty_removed_email('recipient@example.com', 'Faculty')
        self.assertEqual(self.post.call_count, 2)
        for call in self.post.call_args_list:
            self.assertTrue(call.kwargs['json']['textContent'])
            self.assertTrue(call.kwargs['json']['htmlContent'])

    def test_plain_text_and_html_only_messages(self):
        self.assertEqual(self.message().send(), 1)
        self.assertNotIn('htmlContent', self.post.call_args.kwargs['json'])
        message = self.message()
        message.content_subtype = 'html'
        message.body = '<p>Body</p>'
        self.assertEqual(message.send(), 1)
        self.assertNotIn('textContent', self.post.call_args.kwargs['json'])

    def test_empty_batches_and_recipientless_messages_do_not_send(self):
        backend = get_connection()
        self.assertEqual(backend.send_messages(None), 0)
        self.assertEqual(backend.send_messages([]), 0)
        self.assertEqual(backend.send_messages([EmailMessage('Subject', 'Body')]), 0)
        self.post.assert_not_called()

    def test_context_manager_and_batch_count(self):
        with get_connection() as backend:
            self.assertEqual(backend.send_messages([self.message(), self.message()]), 2)

    @override_settings(BREVO_API_KEY='')
    def test_missing_key_fails_before_network(self):
        with self.assertRaisesMessage(BrevoEmailError, 'BREVO_API_KEY is required'):
            self.message().send()
        self.post.assert_not_called()

    def test_http_errors_raise_without_exposing_response_or_key(self):
        for status in (302, 400, 401, 429, 500):
            with self.subTest(status=status):
                self.response.status_code = status
                self.response.text = 'secret-response-content'
                with self.assertLogs('apps.core.email_backends') as logs:
                    with self.assertRaisesMessage(BrevoEmailError, f'HTTP {status}'):
                        self.message().send()
                self.assertNotIn('secret-response-content', str(logs.output))
                self.assertNotIn('test-api-key', str(logs.output))

    def test_timeout_is_sanitized_and_not_retried(self):
        self.post.side_effect = requests.Timeout('secret-request-details')
        with self.assertRaisesMessage(BrevoEmailError, 'connection failed or timed out') as error:
            self.message().send()
        self.assertNotIn('secret-request-details', str(error.exception))
        self.post.assert_called_once()

    def test_fail_silently_continues_batch_and_counts_only_accepted(self):
        successful = MagicMock()
        successful.__enter__.return_value = self.response
        self.post.side_effect = [requests.ConnectionError('private'), successful]
        with get_connection(fail_silently=True) as backend:
            self.assertEqual(backend.send_messages([self.message(), self.message()]), 1)

    def test_message_send_fail_silently_returns_zero(self):
        self.response.status_code = 401
        self.assertEqual(self.message().send(fail_silently=True), 0)

    def test_invalid_acceptance_response_is_not_counted(self):
        for value in ({}, [], None):
            with self.subTest(value=value):
                self.response.json.return_value = value
                with self.assertRaises(BrevoEmailError):
                    self.message().send()
        self.response.json.side_effect = ValueError('private response')
        with self.assertRaisesMessage(BrevoEmailError, 'Invalid Brevo acceptance'):
            self.message().send()

    def test_unsupported_features_fail_before_network(self):
        attached = self.message()
        attached.attach('file.txt', 'data', 'text/plain')
        headers = self.message()
        headers.extra_headers = {'X-Custom': 'value'}
        replies = self.message()
        replies.reply_to = ['one@example.com', 'two@example.com']
        alternative = EmailMultiAlternatives('Subject', 'Body', to=['a@example.com'])
        alternative.attach_alternative('calendar', 'text/calendar')
        for message in (attached, headers, replies, alternative):
            with self.subTest(message=message):
                with self.assertRaises(BrevoEmailError):
                    message.send()
        self.post.assert_not_called()

    def test_header_injection_is_rejected_without_leaking_content(self):
        message = self.message()
        message.subject = 'private\r\nBcc: injected@example.com'
        with self.assertRaisesMessage(BrevoEmailError, 'Invalid email message') as error:
            message.send()
        self.assertNotIn('private', str(error.exception))
        self.post.assert_not_called()


class EmailBackendSelectionTests(SimpleTestCase):
    def backend_for(self, render, configured_backend):
        environment = dict(os.environ, RENDER=render, EMAIL_BACKEND=configured_backend)
        result = subprocess.run(
            [sys.executable, '-c',
             'from config.settings.base import EMAIL_BACKEND; print(EMAIL_BACKEND)'],
            env=environment, capture_output=True, text=True, check=True,
        )
        return result.stdout.strip()

    def test_render_does_not_override_configured_backend(self):
        for value in ('true', 'True'):
            with self.subTest(render=value):
                self.assertEqual(
                    self.backend_for(value, 'django.core.mail.backends.smtp.EmailBackend'),
                    'django.core.mail.backends.smtp.EmailBackend',
                )

    def test_non_render_preserves_configured_backend(self):
        for value in ('false', ''):
            for backend in ('django.core.mail.backends.smtp.EmailBackend',
                            'apps.core.email_backends.BrevoEmailBackend',
                            'django.core.mail.backends.console.EmailBackend'):
                with self.subTest(render=value, backend=backend):
                    self.assertEqual(self.backend_for(value, backend), backend)
