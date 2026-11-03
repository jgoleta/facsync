from types import SimpleNamespace
from unittest.mock import Mock, patch

import requests
from django.test import SimpleTestCase

from apps.faculty.services import google_calendar as calendar


class OAuthDiagnosticTests(SimpleTestCase):
    def attempt(self, response=None, exception=None):
        request = SimpleNamespace(session={'google_calendar_oauth_state': 'state'},
                                  user=SimpleNamespace(email='local@example.com'))
        with patch.object(calendar, '_client_credentials', return_value=('client', 'secret')), \
                patch.object(calendar, 'callback_url', return_value='https://example.com/callback'), \
                patch.object(calendar, '_token_request', return_value={
                    'access_token': 'SECRET_ACCESS', 'refresh_token': 'SECRET_REFRESH',
                    'scope': 'openid email https://www.googleapis.com/auth/calendar.events SECRET_SCOPE',
                }), \
                patch.object(calendar.requests, 'get', return_value=response, side_effect=exception), \
                self.assertLogs(calendar.logger, level='WARNING') as logs, \
                self.assertRaises(calendar.GoogleCalendarError):
            calendar.finish_oauth(request, 'SECRET_CODE', 'state')
        output = '\n'.join(logs.output)
        for secret in ('SECRET_ACCESS', 'SECRET_REFRESH', 'SECRET_SCOPE', 'SECRET_CODE',
                       'PRIVATE_BODY', 'local@example.com', 'other@example.com'):
            self.assertNotIn(secret, output)
        return output

    def test_http_failure_logs_status_and_safe_reason(self):
        response = Mock(ok=False, status_code=403)
        response.json.return_value = {'error': {
            'message': 'PRIVATE_BODY', 'errors': [{'reason': 'insufficientPermissions'}]}}
        output = self.attempt(response=response)
        self.assertIn('http_status=403 reason=insufficientPermissions', output)
        self.assertIn('granted_scopes=email,openid,other_scope', output)
        refs = [line.split('ref=')[1].split()[0] for line in output.splitlines()]
        self.assertEqual(refs[0], refs[1])

    def test_timeout_does_not_log_exception_text(self):
        output = self.attempt(exception=requests.Timeout('PRIVATE_BODY SECRET_ACCESS'))
        self.assertIn('reason=timeout', output)

    def test_successful_http_check_logs_no_identity_data(self):
        response = Mock(ok=True, status_code=200)
        # Stop at the existing email-match guard, without accessing a database.
        response.json.return_value = {'email': 'other@example.com', 'sub': 'PRIVATE_BODY'}
        self.assertIn('outcome=http_success http_status=200', self.attempt(response=response))

    def test_unknown_and_non_json_errors_are_redacted(self):
        response = Mock()
        response.json.return_value = {'error': 'PRIVATE_BODY'}
        self.assertEqual(calendar._userinfo_error_reason(response), 'unclassified')
        response.json.side_effect = ValueError('PRIVATE_BODY')
        self.assertEqual(calendar._userinfo_error_reason(response), 'non_json_response')
        self.assertEqual(calendar._diagnostic_scopes(None), 'not_reported')

    def test_oauth_rejects_token_without_calendar_scope(self):
        request = SimpleNamespace(session={'google_calendar_oauth_state': 'state'},
                                  user=SimpleNamespace(email='local@example.com'))
        with patch.object(calendar, '_client_credentials', return_value=('client', 'secret')), \
                patch.object(calendar, 'callback_url', return_value='https://example.com/callback'), \
                patch.object(calendar, '_token_request', return_value={
                    'access_token': 'SECRET_ACCESS', 'scope': 'openid email profile',
                }), \
                self.assertRaisesRegex(calendar.GoogleCalendarError, 'did not grant the Calendar scope'):
            calendar.finish_oauth(request, 'SECRET_CODE', 'state')

    def test_calendar_scope_is_added_when_deployment_scope_is_stale(self):
        request = SimpleNamespace(session={}, user=SimpleNamespace(email='local@example.com'))
        with patch.object(calendar, 'GOOGLE_CALENDAR_SCOPE', 'openid email profile'), \
                patch.object(calendar, '_client_credentials', return_value=('client', 'secret')):
            url = calendar.start_oauth(request)
        self.assertIn('https%3A%2F%2Fwww.googleapis.com%2Fauth%2Fcalendar.events', url)

    def test_insufficient_calendar_scope_has_reconnect_message(self):
        response = Mock(ok=False, status_code=403)
        response.json.return_value = {'error': {'message': 'Request had insufficient authentication scopes.'}}
        connection = SimpleNamespace()
        with patch.object(calendar, '_access_token', return_value='ACCESS_TOKEN'), \
                patch.object(calendar.requests, 'request', return_value=response), \
                self.assertRaisesRegex(calendar.GoogleCalendarError, 'Disconnect Google Calendar'):
            calendar.google_request(connection, 'GET', '/calendars/primary/events')
