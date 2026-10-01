from unittest.mock import Mock, patch

from django.test import TestCase
from django.urls import reverse

from apps.core.models import User
from apps.faculty.models import FacultyProfile, GoogleCalendarConnection, ScheduleEvent
from apps.faculty.services.google_calendar import GoogleCalendarError, sync_google_calendar


class CalendarImportTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='importer', role='faculty')
        self.faculty = FacultyProfile.objects.create(
            user=self.user, faculty_id='importer', college_id='CCS',
        )
        self.client.force_login(self.user)
        self.url = reverse('faculty:api_schedule_events')

    def connect(self):
        return GoogleCalendarConnection.objects.create(
            user=self.user, google_user_id='importer', access_token='test',
        )

    @patch('apps.faculty.services.google_calendar.google_request')
    def test_other_organizer_invitations_import_across_pages(self, request):
        self.connect()
        invitation = {
            'id': 'invited-event', 'summary': 'Invited meeting',
            'organizer': {'email': 'other@example.com', 'self': False},
            'attendees': [{'self': True, 'responseStatus': 'needsAction'}],
            'start': {'dateTime': '2026-10-02T09:00:00+08:00'},
            'end': {'dateTime': '2026-10-02T10:00:00+08:00'},
        }
        request.side_effect = [
            Mock(json=lambda: {'items': [invitation], 'nextPageToken': 'next'}),
            Mock(json=lambda: {'items': [{
                **invitation, 'id': 'other-consultation',
                'extendedProperties': {'private': {
                    'facsync_type': 'consultation', 'facsync_id': 'another-faculty-request',
                }},
            }]}),
        ]
        response = self.client.get(self.url, {'sync': '1'})
        self.assertTrue(response.json()['sync_performed'])
        self.assertEqual({event['google_event_id'] for event in response.json()['events']},
                         {'invited-event', 'other-consultation'})
        self.assertEqual(request.call_count, 2)
        for call in request.call_args_list:
            self.assertEqual(call.args[1], 'GET')
            self.assertEqual(call.kwargs['params']['showHiddenInvitations'], 'true')
        self.assertEqual(request.call_args.kwargs['params']['pageToken'], 'next')

    @patch('apps.faculty.services.google_calendar.list_google_events')
    def test_import_updates_existing_event_and_returns_it_to_calendar(self, fetch):
        self.connect()
        fetch.return_value = [{
            'id': 'external', 'summary': 'Google meeting', 'location': 'Room 1',
            'description': 'Agenda',
            'start': {'dateTime': '2026-10-02T09:00:00+08:00'},
            'end': {'dateTime': '2026-10-02T10:00:00+08:00'},
        }]
        self.client.get(self.url)
        fetch.assert_not_called()
        response = self.client.get(self.url, {'sync': '1'})
        self.assertTrue(response.json()['sync_performed'])
        self.assertEqual(response.json()['events'][0]['location'], 'Room 1')
        fetch.return_value[0]['summary'] = 'Updated on Google'
        response = self.client.get(self.url, {'sync': '1'})
        self.assertEqual(response.json()['events'][0]['title'], 'Updated on Google')
        self.assertEqual(ScheduleEvent.objects.filter(faculty=self.faculty).count(), 1)

    @patch('apps.faculty.services.google_calendar.list_google_events')
    def test_no_google_access_without_connection_or_enabled_sync(self, fetch):
        for connected in (False, True):
            if connected:
                self.connect()
                self.faculty.sync_enabled = False
                self.faculty.save()
            with self.subTest(connected=connected):
                response = self.client.get(self.url, {'sync': '1'})
                self.assertFalse(response.json()['sync_performed'])
                self.assertTrue(response.json()['sync_error'])
                with self.assertRaises(GoogleCalendarError):
                    sync_google_calendar(self.user)
                fetch.assert_not_called()
                self.assertFalse(ScheduleEvent.objects.exists())

    @patch('apps.faculty.services.google_calendar.list_google_events')
    def test_google_failure_is_not_reported_as_success(self, fetch):
        self.connect()
        fetch.side_effect = GoogleCalendarError('Unable to contact Google Calendar.')
        response = self.client.get(self.url, {'sync': '1'})
        self.assertFalse(response.json()['sync_performed'])
        self.assertIn('Unable to contact', response.json()['sync_error'])
