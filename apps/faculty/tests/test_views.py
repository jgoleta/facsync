import json
from datetime import date, timedelta
from zoneinfo import ZoneInfo

from django.test import TestCase
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.conf import settings
from django.utils import timezone
from unittest.mock import patch

from ..models import ConsultationRequest, FacultyProfile, GoogleCalendarConnection, WalkInQueue
from ..models import ScheduleEvent
from ..services.google_calendar import google_event_payload, refresh_faculty_status, sync_google_calendar


class FacultyViewTests(TestCase):
    def _make_faculty_and_student(self, suffix='walk-in'):
        faculty_user = get_user_model().objects.create_user(
            username=f'faculty-{suffix}',
            password='test-password',
        )
        student = get_user_model().objects.create_user(
            username=f'student-{suffix}',
            password='test-password',
        )
        faculty = FacultyProfile.objects.create(
            faculty_id=f'faculty-{suffix}',
            user=faculty_user,
            college_id='CCS',
        )
        return faculty_user, student, faculty

    def test_faculty_can_toggle_walk_in_availability(self):
        faculty_user, _student, faculty = self._make_faculty_and_student('toggle')
        self.client.force_login(faculty_user)

        response = self.client.post(
            reverse('faculty:api_walk_in_preference'),
            data='{"enabled":true}',
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['walk_ins_enabled'])
        faculty.refresh_from_db()
        self.assertTrue(faculty.walk_ins_enabled)

    def test_student_can_join_only_when_walk_ins_are_enabled(self):
        faculty_user, student, faculty = self._make_faculty_and_student('join')
        self.client.force_login(student)

        response = self.client.post(
            reverse('students:api_join_walk_in_queue'),
            data=json.dumps({'faculty_id': faculty.faculty_id}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(WalkInQueue.objects.count(), 0)

        faculty.walk_ins_enabled = True
        faculty.save(update_fields=['walk_ins_enabled'])
        response = self.client.post(
            reverse('students:api_join_walk_in_queue'),
            data=json.dumps({'faculty_id': faculty.faculty_id, 'message': 'I need help.'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 201)
        queue = WalkInQueue.objects.get()
        self.assertEqual(queue.user, student)
        self.assertEqual(queue.status, 'waiting')

    def test_faculty_can_notify_and_complete_walk_in_student(self):
        faculty_user, student, faculty = self._make_faculty_and_student('lifecycle')
        faculty.walk_ins_enabled = True
        faculty.save(update_fields=['walk_ins_enabled'])
        queue = WalkInQueue.objects.create(
            queue_id='walk-in-lifecycle',
            faculty=faculty,
            user=student,
            position=1,
            joined_at='2026-08-15T09:00:00Z',
        )
        self.client.force_login(faculty_user)

        response = self.client.post(
            reverse('faculty:api_walk_in_detail', args=[queue.queue_id]),
            data='{"action":"notify"}',
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        queue.refresh_from_db()
        self.assertEqual(queue.status, 'called')
        self.assertIsNotNone(queue.notified_at)

        response = self.client.post(
            reverse('faculty:api_walk_in_detail', args=[queue.queue_id]),
            data='{"action":"complete"}',
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        queue.refresh_from_db()
        self.assertEqual(queue.status, 'completed')
        self.assertIsNotNone(queue.served_at)

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
            college_id='CCS',
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

    def test_manual_status_can_be_given_a_future_expiry(self):
        user = get_user_model().objects.create_user(
            username='faculty-temporary-status-test',
            password='test-password',
            role='faculty',
        )
        profile = FacultyProfile.objects.create(
            faculty_id='faculty-temporary-status-test',
            user=user,
            college_id='CCS',
        )
        self.client.force_login(user)
        expiry = timezone.now() + timedelta(hours=2)

        response = self.client.post(
            reverse('faculty:update_status'),
            data=json.dumps({'status': 'busy', 'expires_at': expiry.isoformat()}),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], 'busy')
        self.assertIsNotNone(response.json()['expires_at'])
        profile.refresh_from_db()
        self.assertEqual(profile.manual_status, 'busy')
        self.assertEqual(profile.manual_status_expires_at, expiry)

    def test_expired_manual_status_defaults_to_available(self):
        user = get_user_model().objects.create_user(
            username='faculty-expired-status-test',
            password='test-password',
        )
        profile = FacultyProfile.objects.create(
            faculty_id='faculty-expired-status-test',
            user=user,
            college_id='CCS',
            current_status='busy',
            manual_status='busy',
            manual_status_override=True,
            manual_status_expires_at=timezone.now() - timedelta(minutes=1),
            status_note='In a meeting',
        )

        self.assertEqual(refresh_faculty_status(profile), 'available')
        profile.refresh_from_db()
        self.assertEqual(profile.current_status, 'available')
        self.assertEqual(profile.manual_status, 'available')
        self.assertTrue(profile.manual_status_override)
        self.assertIsNone(profile.manual_status_expires_at)
        self.assertEqual(profile.status_note, '')

    def test_faculty_can_delete_own_completed_consultation(self):
        faculty_user = get_user_model().objects.create_user(
            username='faculty-delete-completed-test',
            password='test-password',
            role='faculty',
        )
        student = get_user_model().objects.create_user(
            username='student-delete-completed-test',
            password='test-password',
        )
        faculty = FacultyProfile.objects.create(
            faculty_id='faculty-delete-completed-test',
            user=faculty_user,
            college_id='CCS',
        )
        consultation = ConsultationRequest.objects.create(
            request_id='delete-completed-test',
            user=student,
            faculty=faculty,
            date=timezone.localdate(),
            status='completed',
        )
        self.client.force_login(faculty_user)

        response = self.client.delete(
            reverse('faculty:api_consultation', args=[consultation.request_id]),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], 'deleted')
        self.assertFalse(ConsultationRequest.objects.filter(pk=consultation.pk).exists())

    def test_status_is_derived_from_an_active_system_calendar_event(self):
        user = get_user_model().objects.create_user(
            username='faculty-calendar-status-test',
            password='test-password',
        )
        faculty = FacultyProfile.objects.create(
            faculty_id='faculty-calendar-status-test',
            user=user,
            college_id='CCS',
        )
        local_now = timezone.localtime(
            timezone.now(),
            ZoneInfo(getattr(settings, 'GOOGLE_CALENDAR_TIME_ZONE', settings.TIME_ZONE)),
        )
        ScheduleEvent.objects.create(
            faculty=faculty,
            title='Current class',
            event_type='busy',
            date=local_now.date(),
            start_time=(local_now - timedelta(minutes=10)).time(),
            end_time=(local_now + timedelta(minutes=10)).time(),
        )

        self.assertEqual(refresh_faculty_status(faculty), 'busy')
        faculty.refresh_from_db()
        self.assertEqual(faculty.current_status, 'busy')

        faculty.manual_status = 'on_leave'
        faculty.manual_status_override = True
        faculty.save(update_fields=['manual_status', 'manual_status_override'])
        self.assertEqual(refresh_faculty_status(faculty), 'on_leave')

        faculty.manual_status = 'available'
        faculty.manual_status_override = False
        faculty.save(update_fields=['manual_status', 'manual_status_override'])
        ScheduleEvent.objects.filter(faculty=faculty).delete()
        self.assertEqual(refresh_faculty_status(faculty), 'available')

    def test_manual_status_can_be_cleared_back_to_calendar_status(self):
        user = get_user_model().objects.create_user(
            username='faculty-status-mode-test',
            password='test-password',
        )
        faculty = FacultyProfile.objects.create(
            faculty_id='faculty-status-mode-test',
            user=user,
            college_id='CCS',
        )
        local_now = timezone.localtime(
            timezone.now(),
            ZoneInfo(getattr(settings, 'GOOGLE_CALENDAR_TIME_ZONE', settings.TIME_ZONE)),
        )
        ScheduleEvent.objects.create(
            faculty=faculty,
            title='Current class',
            event_type='busy',
            date=local_now.date(),
            start_time=(local_now - timedelta(minutes=10)).time(),
            end_time=(local_now + timedelta(minutes=10)).time(),
        )
        self.client.force_login(user)

        response = self.client.post(
            reverse('faculty:update_status'),
            data='{"status":"on-leave","manual_override":true}',
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], 'on_leave')

        response = self.client.post(
            reverse('faculty:update_status'),
            data='{"manual_override":false}',
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], 'busy')
        faculty.refresh_from_db()
        self.assertFalse(faculty.manual_status_override)

    @patch('apps.faculty.views.create_google_event')
    def test_schedule_event_is_created_in_google_and_locally(self, create_google_event):
        user = get_user_model().objects.create_user(
            username='faculty-local-event-test',
            password='test-password',
            role='faculty',
        )
        faculty = FacultyProfile.objects.create(
            faculty_id='faculty-local-event-test',
            user=user,
            college_id='CCS',
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

    @patch('apps.faculty.views.create_google_event')
    def test_schedule_event_can_stay_local_when_google_sync_is_declined(self, create_google_event):
        user = get_user_model().objects.create_user(
            username='faculty-local-only-event-test',
            password='test-password',
            role='faculty',
        )
        faculty = FacultyProfile.objects.create(
            faculty_id='faculty-local-only-event-test',
            user=user,
            college_id='CCS',
        )
        self.client.force_login(user)
        GoogleCalendarConnection.objects.create(
            user=user,
            google_user_id='google-user-local-only',
            access_token='access-token',
            refresh_token='refresh-token',
        )

        response = self.client.post(
            reverse('faculty:api_schedule_events'),
            data='{"title":"Private planning","event_type":"busy","date":"2026-08-20","start_time":"09:00","end_time":"10:00","sync_to_google":false}',
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 201)
        event = faculty.schedule_events.get(title='Private planning')
        self.assertIsNone(event.google_event_id)
        self.assertEqual(event.sync_state, 'local')
        create_google_event.assert_not_called()

    @patch('apps.faculty.views.delete_google_event')
    def test_editing_event_with_google_sync_declined_removes_google_event(self, delete_google_event):
        user = get_user_model().objects.create_user(
            username='faculty-edit-local-only-event-test',
            password='test-password',
            role='faculty',
        )
        faculty = FacultyProfile.objects.create(
            faculty_id='faculty-edit-local-only-event-test',
            user=user,
            college_id='CCS',
        )
        connection = GoogleCalendarConnection.objects.create(
            user=user,
            google_user_id='google-user-edit-local-only',
            access_token='access-token',
            refresh_token='refresh-token',
        )
        event = ScheduleEvent.objects.create(
            faculty=faculty,
            title='Old class title',
            event_type='busy',
            date='2026-08-20',
            start_time='09:00',
            end_time='10:00',
            google_event_id='google-event-to-remove',
            google_calendar_id=connection.calendar_id,
            managed_by_facsync=True,
            sync_state='synced',
        )
        self.client.force_login(user)

        response = self.client.put(
            reverse('faculty:api_schedule_event_detail', args=[event.pk]),
            data='{"title":"Updated class title","sync_to_google":false}',
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        delete_google_event.assert_called_once()
        event.refresh_from_db()
        self.assertEqual(event.title, 'Updated class title')
        self.assertIsNone(event.google_event_id)
        self.assertIsNone(event.google_calendar_id)
        self.assertFalse(event.managed_by_facsync)
        self.assertEqual(event.sync_state, 'local')

    @patch('apps.faculty.views.create_google_event')
    def test_recurring_event_stays_local_when_google_is_connected(self, create_google_event):
        user = get_user_model().objects.create_user(
            username='faculty-recurring-event-test',
            password='test-password',
            role='faculty',
        )
        faculty = FacultyProfile.objects.create(
            faculty_id='faculty-recurring-event-test',
            user=user,
            college_id='CCS',
        )
        self.client.force_login(user)
        GoogleCalendarConnection.objects.create(
            user=user,
            google_user_id='google-user',
            access_token='access-token',
            refresh_token='refresh-token',
        )

        response = self.client.post(
            reverse('faculty:api_schedule_events'),
            data='{"title":"Recurring class","event_type":"busy","date":null,'
                 '"day_of_week":"monday","start_month":8,"end_month":5,'
                 '"start_time":"09:00","end_time":"10:00"}',
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 201)
        event = faculty.schedule_events.get(title='Recurring class')
        self.assertIsNone(event.date)
        self.assertIsNone(event.google_event_id)
        create_google_event.assert_not_called()

    @patch('apps.faculty.services.google_calendar.create_google_event')
    @patch('apps.faculty.services.google_calendar.list_google_events')
    def test_google_events_sync_into_local_schedule(self, list_google_events, create_google_event):
        user = get_user_model().objects.create_user(
            username='faculty-google-import-test',
            password='test-password',
        )
        faculty = FacultyProfile.objects.create(
            faculty_id='faculty-google-import-test',
            user=user,
            college_id='CCS',
        )
        connection = GoogleCalendarConnection.objects.create(
            user=user,
            google_user_id='google-user',
            access_token='access-token',
            refresh_token='refresh-token',
        )
        list_google_events.return_value = [{
            'id': 'google-event-2',
            'summary': 'College Meeting',
            'description': 'Monthly meeting',
            'start': {'dateTime': '2026-08-20T09:00:00+08:00'},
            'end': {'dateTime': '2026-08-20T10:00:00+08:00'},
        }]

        sync_google_calendar(user)

        event = ScheduleEvent.objects.get(faculty=faculty, google_event_id='google-event-2')
        self.assertEqual(event.title, 'College Meeting')
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
            college_id='CCS',
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

    def _make_csv_faculty(self, suffix='csv'):
        user = get_user_model().objects.create_user(
            username=f'faculty-csv-{suffix}',
            password='test-password',
            role='faculty',
        )
        faculty = FacultyProfile.objects.create(
            faculty_id=f'faculty-csv-{suffix}',
            user=user,
            college_id='CCS',
        )
        self.client.force_login(user)
        return faculty

    def test_schedule_template_download_has_canonical_csv_headers(self):
        self._make_csv_faculty('template')

        response = self.client.get(reverse('faculty:schedule_template'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/csv')
        self.assertIn('schedule_template.csv', response['Content-Disposition'])
        self.assertTrue(response.content.startswith(
            b'event_title,short_description,room_location,recurring_day,start_month,end_month,start_time,end_time,status_type'
        ))

    def test_csv_schedule_upload_appends_schedule_and_returns_preview(self):
        faculty = self._make_csv_faculty('upload')
        ScheduleEvent.objects.create(
            faculty=faculty,
            title='Old event',
            event_type='busy',
            date='2026-09-01',
            start_time='08:00',
            end_time='09:00',
        )
        upload = SimpleUploadedFile(
            'schedule.csv',
            b'event_title,short_description,room_location,recurring_day,start_month,end_month,start_time,end_time,status_type\n'
            b'Introductory lecture,Introductory lecture,Room 204,Monday,8,5,09:00,10:30,Busy\n'
            b'Office hours,Student consultations,,Monday,8,5,13:00,15:00,Busy\n',
            content_type='text/csv',
        )

        response = self.client.post(reverse('faculty:upload_schedule'), {'file': upload})

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()['added_count'], 2)
        self.assertEqual(faculty.schedule_events.count(), 3)
        self.assertTrue(faculty.schedule_events.filter(title='Old event').exists())
        self.assertEqual(faculty.schedule_events.get(start_time='09:00').location, 'Room 204')
        self.assertEqual(faculty.schedule_events.get(start_time='13:00').schedule_status, 'Busy')
        self.assertEqual(faculty.schedule_events.get(start_time='09:00').day_of_week, 'monday')
        self.assertEqual(faculty.schedule_events.get(start_time='09:00').start_month, 8)
        self.assertEqual(faculty.schedule_events.get(start_time='09:00').end_month, 5)
        faculty.refresh_from_db()
        self.assertIsNotNone(faculty.schedule_last_updated_at)

    def test_invalid_csv_does_not_delete_existing_schedule(self):
        faculty = self._make_csv_faculty('invalid')
        ScheduleEvent.objects.create(
            faculty=faculty,
            title='Keep this',
            event_type='busy',
            date='2026-09-01',
            start_time='09:00',
            end_time='10:00',
        )
        upload = SimpleUploadedFile(
            'schedule.csv',
            b'event_title,short_description,room_location,recurring_day,start_month,end_month,start_time,end_time,status_type\n'
            b'First,First,Room 1,Monday,8,5,09:00,10:00,Busy\n'
            b'Overlap,Overlap,Room 1,Monday,8,5,09:30,11:00,Busy\n',
        )

        response = self.client.post(reverse('faculty:upload_schedule'), {'file': upload})

        self.assertEqual(response.status_code, 400)
        self.assertTrue(any('overlap' in error.lower() for error in response.json()['errors']))
        self.assertEqual(faculty.schedule_events.count(), 1)
        self.assertEqual(faculty.schedule_events.get().title, 'Keep this')

    def test_csv_none_day_creates_time_only_month_range(self):
        faculty = self._make_csv_faculty('none-day')
        upload = SimpleUploadedFile(
            'schedule.csv',
            b'event_title,short_description,room_location,recurring_day,start_month,end_month,start_time,end_time,status_type\n'
            b'Time only,Time only,,,,,10:30,12:00,Busy\n',
        )

        response = self.client.post(reverse('faculty:upload_schedule'), {'file': upload})

        self.assertEqual(response.status_code, 201)
        event = faculty.schedule_events.get()
        self.assertIsNone(event.date)
        self.assertEqual(event.day_of_week, '')
        self.assertIsNone(event.start_month)
        self.assertIsNone(event.end_month)

    def test_add_event_derives_allocation_months_from_dates(self):
        faculty = self._make_csv_faculty('allocation-dates')

        response = self.client.post(
            reverse('faculty:api_schedule_events'),
            data=json.dumps({
                'title': 'Recurring class',
                'description': 'Weekly class',
                'event_type': 'busy',
                'day_of_week': 'monday',
                'start_date': '2026-08-01',
                'end_date': '2027-05-31',
                'start_time': '10:30',
                'end_time': '12:00',
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 201)
        event = faculty.schedule_events.get()
        self.assertIsNone(event.date)
        self.assertEqual((event.start_month, event.end_month), (8, 5))

    @patch('apps.faculty.views.create_google_event', return_value={'id': 'google-recurring-event'})
    def test_recurring_event_syncs_when_user_chooses_google(self, create_event):
        faculty = self._make_csv_faculty('recurring-google')
        GoogleCalendarConnection.objects.create(
            user=faculty.user,
            google_user_id='google-recurring-user',
            access_token='access-token',
        )

        response = self.client.post(
            reverse('faculty:api_schedule_events'),
            data=json.dumps({
                'title': 'Recurring class',
                'event_type': 'busy',
                'day_of_week': 'monday',
                'start_date': '2026-08-01',
                'end_date': '2027-05-31',
                'start_time': '10:30',
                'end_time': '12:00',
                'sync_to_google': True,
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 201)
        event = faculty.schedule_events.get()
        self.assertEqual(event.google_event_id, 'google-recurring-event')
        self.assertEqual(event.sync_state, 'synced')
        create_event.assert_called_once()

    @patch('apps.faculty.services.google_calendar.timezone.localdate', return_value=date(2026, 9, 2))
    def test_recurring_google_payload_contains_weekly_rule(self, _localdate):
        faculty = self._make_csv_faculty('recurring-payload')
        event = ScheduleEvent.objects.create(
            faculty=faculty,
            title='Monday class',
            event_type='busy',
            day_of_week='monday',
            start_month=8,
            end_month=5,
            start_time='10:30',
            end_time='12:00',
        )
        event.refresh_from_db()

        payload = google_event_payload(event)

        self.assertEqual(payload['start']['dateTime'][:10], '2026-08-03')
        self.assertEqual(payload['recurrence'], ['RRULE:FREQ=WEEKLY;BYDAY=MO;UNTIL=20270531T235959Z'])

    def test_add_event_with_empty_recurring_day_remains_date_based(self):
        faculty = self._make_csv_faculty('date-event')

        response = self.client.post(
            reverse('faculty:api_schedule_events'),
            data=json.dumps({
                'title': 'One-off meeting',
                'event_type': 'busy',
                'date': '2026-08-22',
                'day_of_week': '',
                'start_date': '2026-08-22',
                'end_date': '2026-08-22',
                'start_month': None,
                'end_month': None,
                'start_time': '10:30',
                'end_time': '12:00',
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 201)
        event = faculty.schedule_events.get()
        self.assertEqual(event.date.isoformat(), '2026-08-22')
        self.assertIsNone(event.start_month)

    def test_approved_consultation_is_returned_on_faculty_calendar(self):
        faculty_user = get_user_model().objects.create_user(
            username='faculty-approved-calendar-test',
            password='test-password',
            role='faculty',
        )
        student = get_user_model().objects.create_user(
            username='student-approved-calendar-test',
            password='test-password',
        )
        faculty = FacultyProfile.objects.create(
            faculty_id='faculty-approved-calendar-test',
            user=faculty_user,
            college_id='CCS',
        )
        ConsultationRequest.objects.create(
            request_id='approved-calendar-consultation-test',
            user=student,
            faculty=faculty,
            date='2026-08-24',
            start_time='10:30',
            end_time='11:30',
            status='approved',
        )
        self.client.force_login(faculty_user)

        response = self.client.get(reverse('faculty:api_schedule_events'))

        self.assertEqual(response.status_code, 200)
        consultation_event = next(
            event for event in response.json()['events']
            if event.get('is_consultation')
        )
        self.assertEqual(consultation_event['date'], '2026-08-24')
        self.assertEqual(consultation_event['start_time'], '10:30:00')
        self.assertEqual(consultation_event['end_time'], '11:30:00')
        self.assertIn('student-approved-calendar-test', consultation_event['title'])

    def test_clear_schedule_deletes_only_uploaded_preview_events(self):
        faculty = self._make_csv_faculty('clear')
        ScheduleEvent.objects.create(
            faculty=faculty,
            title='Keep manual event',
            event_type='busy',
            date='2026-09-01',
            start_time='09:00',
            end_time='10:00',
        )

        upload = SimpleUploadedFile(
            'schedule.csv',
            b'event_title,short_description,room_location,recurring_day,start_month,end_month,start_time,end_time,status_type\n'
            b'Remove this,Uploaded row,Room 1,Monday,8,5,11:00,12:00,Busy\n',
            content_type='text/csv',
        )
        upload_response = self.client.post(reverse('faculty:upload_schedule'), {'file': upload})
        uploaded_event_id = upload_response.json()['events'][0]['id']

        response = self.client.post(
            reverse('faculty:clear_schedule'),
            data=json.dumps({'event_ids': [uploaded_event_id]}),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['deleted_count'], 1)
        self.assertTrue(faculty.schedule_events.filter(title='Keep manual event').exists())
        self.assertFalse(faculty.schedule_events.filter(title='Remove this').exists())

    def test_calendar_sync_preference_requires_connection_and_can_be_disabled(self):
        user = get_user_model().objects.create_user(
            username='faculty-calendar-toggle-test',
            password='test-password',
        )
        FacultyProfile.objects.create(
            faculty_id='faculty-calendar-toggle-test',
            user=user,
            college_id='CCS',
        )
        self.client.force_login(user)

        response = self.client.post(
            reverse('faculty:calendar_preference'),
            data='{"sync_enabled":true}',
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 409)

        GoogleCalendarConnection.objects.create(
            user=user,
            google_user_id='google-toggle-user',
            access_token='access-token',
            refresh_token='refresh-token',
        )
        response = self.client.post(
            reverse('faculty:calendar_preference'),
            data='{"sync_enabled":false}',
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(FacultyProfile.objects.get(pk='faculty-calendar-toggle-test').sync_enabled)

    @patch('apps.faculty.views.consultation_has_calendar_conflict', return_value=False)
    @patch('apps.faculty.views.create_consultation_event')
    def test_approving_consultation_creates_google_event(self, create_event, conflict):
        faculty_user = get_user_model().objects.create_user(
            username='faculty-consultation-approval-test',
            email='faculty@example.com',
            password='test-password',
        )
        student = get_user_model().objects.create_user(
            username='student-consultation-approval-test',
            email='student@example.com',
            password='test-password',
        )
        faculty = FacultyProfile.objects.create(
            faculty_id='faculty-consultation-approval-test',
            user=faculty_user,
            college_id='CCS',
            sync_enabled=True,
        )
        GoogleCalendarConnection.objects.create(
            user=faculty_user,
            google_user_id='google-consultation-user',
            access_token='access-token',
            refresh_token='refresh-token',
        )
        consultation = ConsultationRequest.objects.create(
            request_id='consultation-approval-test',
            user=student,
            faculty=faculty,
            date='2026-08-20',
            start_time='09:00',
            end_time='10:00',
        )
        create_event.return_value = {'id': 'consultation-google-event'}
        self.client.force_login(faculty_user)

        response = self.client.post(
            reverse('faculty:api_consultation', args=[consultation.request_id]),
            data='{"status":"approved"}',
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        consultation.refresh_from_db()
        self.assertEqual(consultation.google_event_id, 'consultation-google-event')
        self.assertEqual(consultation.calendar_sync_status, 'synced')
        create_event.assert_called_once()

    @patch('apps.faculty.views.delete_consultation_event')
    @patch('apps.faculty.views.update_consultation_event')
    def test_reschedule_and_cancel_update_and_delete_google_event(self, update_event, delete_event):
        faculty_user = get_user_model().objects.create_user(
            username='faculty-consultation-edit-test',
            email='faculty-edit@example.com',
            password='test-password',
        )
        student = get_user_model().objects.create_user(
            username='student-consultation-edit-test',
            email='student-edit@example.com',
            password='test-password',
        )
        faculty = FacultyProfile.objects.create(
            faculty_id='faculty-consultation-edit-test',
            user=faculty_user,
            college_id='CCS',
            sync_enabled=True,
        )
        GoogleCalendarConnection.objects.create(
            user=faculty_user,
            google_user_id='google-edit-user',
            access_token='access-token',
            refresh_token='refresh-token',
        )
        consultation = ConsultationRequest.objects.create(
            request_id='consultation-edit-test',
            user=student,
            faculty=faculty,
            date='2026-08-20',
            start_time='09:00',
            end_time='10:00',
            status='approved',
            google_event_id='consultation-edit-event',
            google_calendar_id='primary',
        )
        self.client.force_login(faculty_user)

        response = self.client.patch(
            reverse('faculty:api_consultation', args=[consultation.request_id]),
            data='{"date":"2026-08-21","start_time":"11:00","end_time":"12:00"}',
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        consultation.refresh_from_db()
        self.assertEqual(consultation.date.isoformat(), '2026-08-21')
        update_event.assert_called_once()

        response = self.client.delete(
            reverse('faculty:api_consultation', args=[consultation.request_id]),
        )
        self.assertEqual(response.status_code, 200)
        consultation.refresh_from_db()
        self.assertEqual(consultation.status, 'cancelled')
        self.assertIsNone(consultation.google_event_id)
        delete_event.assert_called_once()
