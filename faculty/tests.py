from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model
from unittest.mock import patch

from .models import FacultyProfile, GoogleCalendarConnection
from .models import ScheduleEvent
from .facultyServices.googleCalendarService import sync_google_calendar


class FacultyViewTests(TestCase):
    def test_dashboard_page_renders(self):
        user = get_user_model().objects.create_user(
            username='faculty-dashboard-test',
            password='test-password',
        )
        self.client.force_login(user)
        response = self.client.get(reverse('faculty:dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'faculty/dashboardFaculty.html')

    def test_status_update_persists_status_note_and_history(self):
        user = get_user_model().objects.create_user(
            username='faculty-status-test',
            password='test-password',
        )
        FacultyProfile.objects.create(
            faculty_id='faculty-status-test',
            user=user,
            department_id='CCS',
        )
        self.client.force_login(user)

        response = self.client.post(
            reverse('faculty:update_status'),
            data='{"status":"on-leave","note":"Out of office today"}',
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], 'on_leave')
        profile = FacultyProfile.objects.get(pk='faculty-status-test')
        self.assertEqual(profile.current_status, 'on_leave')
        self.assertEqual(profile.status_note, 'Out of office today')
        self.assertEqual(profile.status_history.count(), 1)

    @patch('faculty.views.create_google_event')
    def test_schedule_event_is_created_in_google_and_locally(self, create_google_event):
        user = get_user_model().objects.create_user(
            username='faculty-local-event-test',
            password='test-password',
        )
        faculty = FacultyProfile.objects.create(
            faculty_id='faculty-local-event-test',
            user=user,
            department_id='CCS',
        )
        self.client.force_login(user)
        GoogleCalendarConnection.objects.create(
            user=user,
            google_user_id='google-user',
            access_token='access-token',
            refresh_token='refresh-token',
        )
        create_google_event.return_value = {'id': 'google-event-1'}

        response = self.client.post(
            reverse('faculty:api_schedule_events'),
            data='{"title":"Local planning","event_type":"busy","date":"2026-08-20","start_time":"09:00","end_time":"10:00"}',
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 201)
        event = faculty.schedule_events.get(title='Local planning')
        self.assertEqual(event.google_event_id, 'google-event-1')
        create_google_event.assert_called_once()

    @patch('faculty.facultyServices.googleCalendarService.create_google_event')
    @patch('faculty.facultyServices.googleCalendarService.list_google_events')
    def test_google_events_sync_into_local_schedule(self, list_google_events, create_google_event):
        user = get_user_model().objects.create_user(
            username='faculty-google-import-test',
            password='test-password',
        )
        faculty = FacultyProfile.objects.create(
            faculty_id='faculty-google-import-test',
            user=user,
            department_id='CCS',
        )
        connection = GoogleCalendarConnection.objects.create(
            user=user,
            google_user_id='google-user',
            access_token='access-token',
            refresh_token='refresh-token',
        )
        list_google_events.return_value = [{
            'id': 'google-event-2',
            'summary': 'Department Meeting',
            'description': 'Monthly meeting',
            'start': {'dateTime': '2026-08-20T09:00:00+08:00'},
            'end': {'dateTime': '2026-08-20T10:00:00+08:00'},
        }]

        sync_google_calendar(user)

        event = ScheduleEvent.objects.get(faculty=faculty, google_event_id='google-event-2')
        self.assertEqual(event.title, 'Department Meeting')
        self.assertEqual(event.date.isoformat(), '2026-08-20')
        self.assertEqual(event.start_time.isoformat(), '09:00:00')
        self.assertEqual(event.google_calendar_id, connection.calendar_id)
        create_google_event.assert_not_called()

    def test_booking_page_renders(self):
        user = get_user_model().objects.create_user(
            username='faculty-booking-test',
            password='test-password',
        )
        self.client.force_login(user)
        response = self.client.get(reverse('faculty:booking_management'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'faculty/bookingManagement.html')

    def test_profile_page_renders(self):
        user = get_user_model().objects.create_user(
            username='faculty-profile-test',
            password='test-password',
        )
        self.client.force_login(user)
        response = self.client.get(reverse('faculty:profile'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'faculty/profile.html')

    def test_profile_updates_editable_fields(self):
        user = get_user_model().objects.create_user(
            username='faculty-profile-save-test',
            password='test-password',
        )
        FacultyProfile.objects.create(
            faculty_id='faculty-profile-save-test',
            user=user,
            department_id='CCS',
        )
        self.client.force_login(user)

        response = self.client.post(
            reverse('faculty:profile'),
            {'field': 'office_location', 'value': 'Room 204'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['value'], 'Room 204')
        self.assertEqual(
            FacultyProfile.objects.get(pk='faculty-profile-save-test').office_location,
            'Room 204',
        )

    def test_schedule_page_renders(self):
        user = get_user_model().objects.create_user(
            username='faculty-schedule-test',
            password='test-password',
        )
        self.client.force_login(user)
        response = self.client.get(reverse('faculty:schedule'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'faculty/scheduleFaculty.html')
        self.assertContains(response, f'href="{reverse("faculty:booking_management")}"')
