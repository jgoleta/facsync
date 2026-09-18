from datetime import date, datetime, time, timezone
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.depthead.services.schedule_availability import get_schedule_availability
from apps.faculty.models import ConsultationRequest, FacultyProfile, ScheduleEvent, StatusHistory


@override_settings(GOOGLE_CALENDAR_TIME_ZONE='Asia/Manila')
class ScheduleAvailabilityTests(TestCase):
    monday = date(2026, 9, 14)

    def faculty(self, name, college='CCS', status='active'):
        user = get_user_model().objects.create(
            username=name, role='faculty', college=college, account_status=status,
        )
        return FacultyProfile.objects.create(faculty_id=name, user=user, college_id=college)

    def event(self, faculty, **kwargs):
        values = dict(title='Class', date=self.monday, start_time=time(8), end_time=time(17))
        values.update(kwargs)
        return ScheduleEvent.objects.create(faculty=faculty, **values)

    def summary(self):
        return get_schedule_availability('ccs', today=self.monday)

    def test_no_records_excluded_from_ranking_but_included_in_percentage(self):
        self.faculty('No schedule')
        booked = self.faculty('Booked')
        self.event(booked)
        result = self.summary()
        monday = result['rows'][0]
        self.assertEqual(monday['winners'], [])
        self.assertEqual(monday['ranking_empty'], 'No open time')
        self.assertEqual(monday['open_minutes'], 0)
        self.assertEqual(monday['availability_percent'], 50)
        self.assertEqual(result['rows'][1]['winners'], ['Booked'])

    def test_only_unscheduled_faculty_and_empty_college(self):
        self.faculty('Unscheduled')
        row = self.summary()['rows'][0]
        self.assertEqual(row['ranking_empty'], 'No recorded schedules')
        self.assertEqual(row['availability_percent'], 100)
        empty = get_schedule_availability('CBA', today=self.monday)
        self.assertIsNone(empty['rows'][0]['availability_percent'])
        self.assertEqual(empty['rows'][0]['winners'], [])

    def test_recurring_and_dated_events_bucket_by_actual_occurrence(self):
        faculty = self.faculty('Teacher')
        self.event(faculty, date=None, day_of_week='monday',
                   recurrence_start_date=self.monday, recurrence_end_date=date(2026, 9, 20))
        self.event(faculty, date=date(2026, 9, 16), day_of_week='friday')
        self.event(faculty, date=date(2026, 9, 8))
        rows = self.summary()['rows']
        self.assertEqual([r['availability_percent'] for r in rows], [0, 100, 0, 100, 100, 100, 100])

    def test_recurrence_bounds_exclusions_and_legacy_month_ranges(self):
        faculty = self.faculty('Teacher')
        cases = [
            {'recurrence_excluded_dates': ['2026-09-14']},
            {'recurrence_start_date': date(2026, 9, 15)},
            {'recurrence_end_date': date(2026, 9, 13)},
            {'start_month': 10, 'end_month': 2},
        ]
        for extra in cases:
            with self.subTest(extra=extra):
                event = self.event(faculty, date=None, day_of_week='monday', **extra)
                self.assertEqual(self.summary()['rows'][0]['open_minutes'], 540)
                event.delete()
        self.event(faculty, date=None, day_of_week='monday', start_month=9, end_month=2)
        self.assertEqual(self.summary()['rows'][0]['open_minutes'], 0)

    def test_overlaps_clipping_and_exact_threshold(self):
        faculty = self.faculty('Teacher')
        self.event(faculty, start_time=time(6), end_time=time(12))
        self.event(faculty, start_time=time(10), end_time=time(16))
        self.event(faculty, start_time=time(17), end_time=time(19))
        row = self.summary()['rows'][0]
        self.assertEqual(row['open_minutes'], 60)
        self.assertEqual(row['availability_percent'], 100)
        self.event(faculty, start_time=time(16), end_time=time(16, 1))
        self.assertEqual(self.summary()['rows'][0]['availability_percent'], 0)

    def test_fragmented_free_time_does_not_meet_threshold(self):
        faculty = self.faculty('Teacher')
        self.event(faculty, start_time=time(8, 30), end_time=time(16, 30))
        row = self.summary()['rows'][0]
        self.assertEqual(row['open_minutes'], 60)
        self.assertEqual(row['availability_percent'], 0)

    def test_all_day_and_overnight_spillover(self):
        faculty = self.faculty('Teacher')
        self.event(faculty, date=date(2026, 9, 13), start_time=time(23), end_time=time(10))
        self.event(faculty, date=date(2026, 9, 15), start_time=None, end_time=None)
        rows = self.summary()['rows']
        self.assertEqual(rows[0]['open_minutes'], 420)
        self.assertEqual(rows[1]['open_minutes'], 0)

    def test_ties_scope_and_status_consultation_independence(self):
        for name in ('Alpha', 'Beta'):
            faculty = self.faculty(name)
            self.event(faculty, start_time=time(8), end_time=time(9), event_type='virtual')
            faculty.current_status = 'on_leave'
            faculty.save(update_fields=['current_status'])
            StatusHistory.objects.create(history_id=name, faculty=faculty, status='on_leave',
                                         changed_at=datetime(2026, 9, 14, tzinfo=timezone.utc))
            ConsultationRequest.objects.create(request_id=name, faculty=faculty, user=faculty.user,
                                               date=self.monday, start_time=time(9), end_time=time(17), status='approved')
        self.event(self.faculty('Other college', 'CBA'))
        self.event(self.faculty('Inactive', status='deactivated'))
        with self.assertNumQueries(2):
            result = self.summary()
        self.assertEqual(result['faculty_count'], 2)
        self.assertEqual(result['rows'][0]['winners'], ['Alpha', 'Beta'])
        self.assertEqual(result['rows'][0]['open_minutes'], 480)

    def test_stale_external_events_do_not_occupy_time_or_qualify_for_ranking(self):
        faculty = self.faculty('Teacher')
        event = self.event(faculty, google_event_id='external', sync_state='out_of_sync')
        self.assertEqual(self.summary()['rows'][0]['availability_percent'], 100)
        self.assertEqual(self.summary()['rows'][0]['winners'], [])
        event.sync_state = 'synced'
        event.save()
        self.assertEqual(self.summary()['rows'][0]['availability_percent'], 0)

    @patch('apps.depthead.services.schedule_availability.timezone.now')
    def test_week_uses_calendar_timezone(self, now):
        now.return_value = datetime(2026, 9, 13, 17, tzinfo=timezone.utc)
        self.assertEqual(get_schedule_availability('CCS')['week_start'], self.monday)

    def test_view_renders_tables_and_caveat(self):
        head = get_user_model().objects.create(username='head', role='depthead', college='CCS')
        self.client.force_login(head)
        response = self.client.get(reverse('depthead:faculty_trends'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Most available faculty per day')
        self.assertContains(response, 'College-wide availability by day')
        self.assertContains(response, 'Based on recorded schedules')
        self.assertContains(response, 'No faculty data')

    @patch('apps.depthead.views.get_faculty_trends')
    def test_charts_distinguish_tiny_zero_and_missing_rates(self, trends):
        items = []
        for name, rate in [('Tiny', 0.08), ('Zero', 0), ('Unknown', None)]:
            faculty = self.faculty(name)
            items.append({
                'faculty_key': f'faculty:{faculty.pk}',
                'last_update_at': None, 'updates_per_day': 0,
                'completion_rate_percent': None, 'average_approval_response_hours': None,
                'availability_rate_percent': rate,
            })
        trends.return_value = {'items': items, 'consultation_period': {'start_date': '2026-09-01', 'end_date': '2026-09-14'}}
        head = get_user_model().objects.create(username='chart-head', role='depthead', college='CCS')
        self.client.force_login(head)
        response = self.client.get(reverse('depthead:faculty_trends'))
        self.assertContains(response, 'history-bar-positive', count=1)
        self.assertContains(response, 'style="width: 0.08%;"')
        self.assertContains(response, 'style="width: 0%;"')
        self.assertContains(response, 'No status history', count=1)
        self.assertContains(response, '0.08%')
        self.assertContains(response, 'height="200"', count=7)
        self.assertContains(response, '(3 of 3)', count=14)
        self.assertContains(response, 'class="trends-chart-pair"', count=1)
        self.assertContains(response, 'Avg. time to approval')
        self.assertContains(response, 'Sep 1')
        self.assertContains(response, 'faculty_trends.css')
        self.assertNotContains(response, '8am?5pm')

    @patch('apps.depthead.services.schedule_availability.timezone.now')
    def test_schedule_chart_renders_zero_as_zero_height(self, now):
        now.return_value = datetime(2026, 9, 14, 4, tzinfo=timezone.utc)
        self.event(self.faculty('Booked'))
        head = get_user_model().objects.create(username='zero-head', role='depthead', college='CCS')
        self.client.force_login(head)
        response = self.client.get(reverse('depthead:faculty_trends'))
        self.assertContains(response, 'height="0"', count=1)
        self.assertContains(response, '(0 of 1)', count=2)
