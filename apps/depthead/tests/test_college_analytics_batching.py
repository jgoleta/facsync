from datetime import date, datetime, time, timedelta, timezone
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse

from apps.core.models import User
from apps.faculty.models import FacultyProfile, ConsultationRequest, WalkInQueue, StatusHistory
from apps.depthead.services import analytics
from apps.depthead.services.analytics_browser import ANALYTICS_QUESTIONS
from . import legacy_college_analytics as legacy
from . import test_faculty_trends_batching as fixtures


class CollegeAnalyticsBatchingTests(TestCase):
    now = fixtures.FacultyTrendsBatchingTests.now
    setUp = fixtures.FacultyTrendsBatchingTests.setUp
    add_faculty = fixtures.FacultyTrendsBatchingTests.add_faculty

    def populate_edges(self):
        faculty = FacultyProfile.objects.get(pk='batch-1')
        start = datetime(2026, 9, 1, tzinfo=timezone(timedelta(hours=8)))
        for i in range(30):
            student, _ = User.objects.get_or_create(username=f'edge-student-{i % 6}', defaults={'role': 'student'})
            scheduled = date(2026, 8, 1) + timedelta(days=i * 2)
            submitted = start + timedelta(days=i - 2, hours=23)
            request = ConsultationRequest.objects.create(
                request_id=f'edge-{i}', faculty=faculty, user=student,
                date=scheduled, status=('completed', 'approved', 'pending', 'declined', 'cancelled')[i % 5],
                agenda=ConsultationRequest.AGENDA_CHOICES[i % 4][0],
                start_time=time(9) if i % 2 else None, end_time=time(10) if i % 3 else None,
                approved_at=submitted+timedelta(hours=(i % 4)-1) if i % 3 else None,
            )
            ConsultationRequest.objects.filter(pk=request.pk).update(requested_at=submitted)
        # Inclusive start and exclusive next-day end of the reporting period;
        # scheduled-date and submission-date populations deliberately disagree.
        for i, submitted in enumerate((start-timedelta(microseconds=1), start,
                                       start+timedelta(days=19)-timedelta(microseconds=1),
                                       start+timedelta(days=19))):
            request = ConsultationRequest.objects.create(request_id=f'boundary-{i}', faculty=faculty,
                user=self.student, date=date(2026, 10, 1), status='completed')
            ConsultationRequest.objects.filter(pk=request.pk).update(requested_at=submitted)
        for i, (moment, status) in enumerate(((start-timedelta(seconds=1), 'available'),
                                             (start, 'busy'), (self.now, 'available'))):
            StatusHistory.objects.create(history_id=f'period-boundary-{i}', faculty=faculty,
                                         changed_at=moment, status=status)
        # Equal completed peaks and tied faculty loads must keep their ordering.
        for i, scheduled in enumerate((date(2026, 7, 6), date(2026, 7, 7))):
            ConsultationRequest.objects.create(request_id=f'tie-{i}', faculty=faculty,
                user=self.student, date=scheduled, status='completed', start_time=time(9+i))
        for i, (notified, served) in enumerate(((None, None), (5, 10), (-1, -2), (10, 5), (0, 0))):
            joined = start + timedelta(days=i)
            WalkInQueue.objects.create(queue_id=f'walk-{i}', faculty=faculty, user=self.student,
                position=i, status=WalkInQueue.QUEUE_STATUS_CHOICES[i % 4][0], joined_at=joined,
                notified_at=joined+timedelta(minutes=notified) if notified is not None else None,
                served_at=joined+timedelta(minutes=served) if served is not None else None)

    @patch('apps.depthead.services.analytics.timezone.now')
    def test_fixed_query_budget_and_complete_page_parity_at_three_and_fifteen(self, clock):
        clock.return_value = self.now
        for i in range(3):
            self.add_faculty(i)
        self.add_faculty(90, college='CBA')
        self.add_faculty(91, active=False)
        self.populate_edges()
        for size in (3, 15):
            if size == 15:
                for i in range(3, 15):
                    self.add_faculty(i)
            with self.subTest(faculty_count=size):
                expected = legacy.get_college_analytics('CCS')
                with self.assertNumQueries(7):
                    actual = analytics.get_college_analytics('CCS')
                self.assertEqual(actual, expected)
                for page in ('admin_dashboard', 'peak_analytics', 'student_behavior'):
                    with self.subTest(page=page):
                        # Nine profiler queries plus the real database session lookup.
                        with self.assertNumQueries(10):
                            response = self.client.get(reverse(f'depthead:{page}'))
                        with patch('apps.depthead.views.get_college_analytics', legacy.get_college_analytics):
                            old = self.client.get(reverse(f'depthead:{page}'))
                        self.assertEqual(response.status_code, 200)
                        self.assertEqual(response.content, old.content)

    @patch('apps.depthead.services.analytics.timezone.now')
    def test_empty_historical_future_timezone_and_confidence_parity(self, clock):
        clock.return_value = self.now
        self.assertEqual(analytics.get_college_analytics('CCS'), legacy.get_college_analytics('CCS'))
        for i in range(15):
            self.add_faculty(i)
        self.populate_edges()
        for start, end in ((date(2026, 8, 1), date(2026, 8, 31)),
                           (date(2026, 7, 1), date(2026, 7, 31)),
                           (date(2026, 9, 1), date(2026, 9, 19)),
                           (date(2026, 4, 1), date(2026, 9, 19)),
                           (date(2026, 10, 1), date(2026, 10, 31)),
                           (date(2025, 1, 1), date(2025, 1, 1))):
            for zone in ('Asia/Manila', 'UTC', 'America/New_York'):
                with self.subTest(start=start, end=end, zone=zone):
                    self.assertEqual(analytics.get_college_analytics(' CCS ', start, end, zone),
                                     legacy.get_college_analytics(' CCS ', start, end, zone))

    @patch('apps.depthead.services.analytics.timezone.now')
    def test_all_browser_answers_match_frozen_public_helpers(self, clock):
        clock.return_value = self.now
        for i in range(15):
            self.add_faculty(i)
        self.populate_edges()
        for metric in ANALYTICS_QUESTIONS:
            with self.subTest(metric=metric):
                response = self.client.get(reverse('depthead:analytics_browser_api'), {'metric': metric})
                with patch('apps.depthead.services.analytics_browser.analytics', legacy):
                    old = self.client.get(reverse('depthead:analytics_browser_api'), {'metric': metric})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json(), old.json())
