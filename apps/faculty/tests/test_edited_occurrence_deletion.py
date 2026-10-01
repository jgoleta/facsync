from datetime import date
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse

from apps.core.models import User
from apps.faculty.models import FacultyProfile, GoogleCalendarConnection, ScheduleEvent
from apps.faculty.services.google_calendar import GoogleCalendarError


class EditedOccurrenceDeletionTests(TestCase):
    def setUp(self):
        user = User.objects.create_user(username='edited-delete', role='faculty')
        self.faculty = FacultyProfile.objects.create(
            user=user, faculty_id='edited-delete', college_id='CCS',
        )
        GoogleCalendarConnection.objects.create(
            user=user, google_user_id='edited-delete', access_token='test-token',
        )
        self.series = ScheduleEvent.objects.create(
            faculty=self.faculty, title='Friday series', day_of_week='friday',
            start_month=10, end_month=10,
            recurrence_excluded_dates=['2026-10-16'],
        )
        self.client.force_login(user)

    def occurrence(self):
        return ScheduleEvent.objects.create(
            faculty=self.faculty, title='Edited Saturday', date=date(2026, 10, 17),
            recurring_parent=self.series, original_occurrence_date=date(2026, 10, 16),
            google_event_id='edited-google-event', google_calendar_id='primary',
            managed_by_facsync=True, sync_state='synced',
        )

    @patch('apps.faculty.services.google_calendar.google_request')
    def test_delete_completes_when_google_event_exists_or_is_already_deleted(self, request):
        for code in (None, 404, 410):
            with self.subTest(code=code):
                event = self.occurrence()
                request.reset_mock()
                request.side_effect = (GoogleCalendarError(
                    f'Google Calendar request failed ({code}): Resource has been deleted.'
                ) if code else None)
                response = self.client.delete(reverse(
                    'faculty:api_schedule_event_detail', args=[event.pk],
                ))
                self.assertEqual(response.status_code, 200, response.content)
                self.assertFalse(ScheduleEvent.objects.filter(pk=event.pk).exists())
                self.series.refresh_from_db()
                self.assertEqual(self.series.recurrence_excluded_dates, ['2026-10-16'])
                self.assertEqual(request.call_args.args[1:], (
                    'DELETE', '/calendars/primary/events/edited-google-event',
                ))

    @patch('apps.faculty.services.google_calendar.google_request')
    def test_permission_failure_keeps_edited_occurrence_for_retry(self, request):
        event = self.occurrence()
        request.side_effect = GoogleCalendarError('Google Calendar request failed (403).')
        response = self.client.delete(reverse(
            'faculty:api_schedule_event_detail', args=[event.pk],
        ))
        self.assertEqual(response.status_code, 502)
        self.assertTrue(ScheduleEvent.objects.filter(pk=event.pk).exists())

    @patch('apps.faculty.services.google_calendar.google_request')
    def test_delete_all_removes_series_and_edited_occurrence(self, request):
        self.series.google_event_id = 'series-google-event'
        self.series.google_calendar_id = 'primary'
        self.series.save()
        edited = self.occurrence()
        unrelated = ScheduleEvent.objects.create(
            faculty=self.faculty, title='Other event', date=date(2026, 10, 20),
        )
        response = self.client.delete(reverse(
            'faculty:api_schedule_event_detail', args=[self.series.pk],
        ))
        self.assertEqual(response.status_code, 200, response.content)
        self.assertFalse(ScheduleEvent.objects.filter(pk__in=[self.series.pk, edited.pk]).exists())
        self.assertTrue(ScheduleEvent.objects.filter(pk=unrelated.pk).exists())
        self.assertEqual({call.args[2] for call in request.call_args_list}, {
            '/calendars/primary/events/series-google-event',
            '/calendars/primary/events/edited-google-event',
        })

    @patch('apps.faculty.views.delete_google_event_instance')
    def test_delete_this_preserves_series_and_other_edited_occurrence(self, delete_instance):
        self.series.google_event_id = 'series-google-event'
        self.series.save()
        edited = self.occurrence()
        response = self.client.delete(
            reverse('faculty:api_schedule_event_detail', args=[self.series.pk])
            + '?occurrence_date=2026-10-23',
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.series.refresh_from_db()
        self.assertEqual(self.series.recurrence_excluded_dates, ['2026-10-16', '2026-10-23'])
        self.assertTrue(ScheduleEvent.objects.filter(pk=edited.pk).exists())
        self.assertEqual(delete_instance.call_args.args[1:], ('series-google-event', date(2026, 10, 23)))
