from datetime import datetime, date, timedelta, timezone
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse

from apps.core.models import User
from apps.faculty.models import FacultyProfile, StatusHistory, ConsultationRequest, ScheduleEvent
from apps.depthead.services.analytics import get_faculty_trends
from .legacy_faculty_trends import get_faculty_trends as legacy_trends


class FacultyTrendsBatchingTests(TestCase):
    now = datetime(2026, 9, 19, 4, tzinfo=timezone.utc)

    def setUp(self):
        self.head = User.objects.create(username='batch-head', role='depthead', college='CCS')
        self.student = User.objects.create(username='batch-student', role='student', college='CCS')
        self.client.force_login(self.head)

    def add_faculty(self, index, college='CCS', active=True):
        user = User.objects.create(username=f'batch-{index}', role='faculty', college=college,
                                   account_status='active' if active else 'deactivated')
        profile = FacultyProfile.objects.create(faculty_id=f'batch-{index}', user=user, college_id=college)
        start = self.now - timedelta(days=7)
        # Missing history, carry-in only, partial history, boundary changes,
        # and unknown/virtual statuses all repeat across the larger roster.
        events = [[], [(start-timedelta(days=1), 'available')],
                  [(start+timedelta(hours=2), 'busy'), (self.now-timedelta(hours=1), 'available')],
                  [(start-timedelta(seconds=1), 'available'), (start, 'busy'),
                   (self.now-timedelta(hours=3), 'available'), (self.now, 'on_leave'),
                   (self.now+timedelta(days=1), 'busy')],
                  [(start, 'not_set'), (start+timedelta(days=2), 'virtual_only')]][index % 5]
        for i, (changed_at, status) in enumerate(events):
            StatusHistory.objects.create(history_id=f'h-{index}-{i}', faculty=profile,
                                         changed_at=changed_at, status=status)
        if index % 5 != 0:
            for i, (status, hours) in enumerate([('completed', 2), ('approved', 0),
                                                ('declined', -1), ('cancelled', None), ('pending', 1.25)]):
                requested = self.now-timedelta(days=3)
                request = ConsultationRequest.objects.create(
                    request_id=f'r-{index}-{i}', user=self.student, faculty=profile,
                    date=date(2026, 9, 18), status=status,
                    approved_at=requested+timedelta(hours=hours) if hours is not None else None)
                ConsultationRequest.objects.filter(pk=request.pk).update(requested_at=requested)
            ConsultationRequest.objects.create(request_id=f'outside-{index}', user=self.student,
                                               faculty=profile, date=date(2026, 8, 1), status='completed')
        ScheduleEvent.objects.create(faculty=profile, title='Class', date=date(2026, 9, 18))

    @patch('apps.depthead.services.analytics.timezone.now')
    def test_output_parity_and_fixed_page_queries_at_three_and_fifteen(self, clock):
        clock.return_value = self.now
        for i in range(3):
            self.add_faculty(i)
        self.add_faculty(90, college='CBA')
        self.add_faculty(91, active=False)
        for size in (3, 15):
            if size == 15:
                for i in range(3, 15):
                    self.add_faculty(i)
            with self.subTest(faculty_count=size):
                expected = legacy_trends('CCS')
                with self.assertNumQueries(4):
                    actual = get_faculty_trends('CCS')
                self.assertEqual(actual, expected)
                self.assertEqual(len(actual['items']), size)
                # Includes real session and authenticated-user lookups. The
                # live profiler excludes the session lookup, so expects eight.
                with self.assertNumQueries(9):
                    response = self.client.get(reverse('depthead:faculty_trends'))
                self.assertEqual(response.status_code, 200)
                self.assertEqual(len(response.context['trends']), size)
                with patch('apps.depthead.views.get_faculty_trends', legacy_trends):
                    old_response = self.client.get(reverse('depthead:faculty_trends'))
                for key in ('trends', 'chart_bars', 'schedule_availability', 'consultation_start', 'consultation_end'):
                    self.assertEqual(response.context[key], old_response.context[key])

    @patch('apps.depthead.services.analytics.timezone.now')
    def test_empty_and_historical_and_future_periods(self, clock):
        clock.return_value = self.now
        self.assertEqual(get_faculty_trends('CCS'), legacy_trends('CCS'))
        for i in range(15):
            self.add_faculty(i)
        for start, end in [(date(2026, 8, 1), date(2026, 8, 31)),
                           (date(2026, 9, 1), date(2026, 9, 12)),
                           (date(2026, 10, 1), date(2026, 10, 31))]:
            with self.subTest(start=start, end=end):
                self.assertEqual(get_faculty_trends('CCS', start, end), legacy_trends('CCS', start, end))
