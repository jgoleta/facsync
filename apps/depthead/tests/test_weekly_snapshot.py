from datetime import datetime, date, time, timedelta
from zoneinfo import ZoneInfo
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse
from apps.core.models import User
from apps.faculty.models import FacultyProfile, ConsultationRequest, StatusHistory
from apps.depthead.services.analytics import (
    current_week_period, get_hourly_availability_snapshot, get_faculty_trends,
)


class WeeklySnapshotTests(TestCase):
    now = datetime(2026, 10, 5, 10, 30, tzinfo=ZoneInfo('Asia/Manila'))

    def setUp(self):
        self.head = User.objects.create(username='head', role='depthead', college='CCS')
        self.student = User.objects.create(username='student', role='student', college='CCS')
        self.faculty = self.make_faculty('Lance', 'CCS')
        self.other = self.make_faculty('Other', 'CBA')
        self.client.force_login(self.head)
        clock = patch('apps.depthead.services.analytics.timezone.now', return_value=self.now)
        clock.start()
        self.addCleanup(clock.stop)

    def make_faculty(self, name, college):
        user = User.objects.create(username=name, first_name=name, role='faculty',
                                   college=college, account_status='active')
        return FacultyProfile.objects.create(faculty_id=name, user=user,
                                             college_id=college, current_status='available')

    def request(self, key, start, end, status='approved', faculty=None, day=None):
        return ConsultationRequest.objects.create(
            request_id=key, user=self.student, faculty=faculty or self.faculty,
            date=day or self.now.date(), start_time=start, end_time=end, status=status,
        )

    def test_hour_overlap_boundaries_and_college_scope(self):
        self.request('overlap', time(9, 30), time(10, 30))
        self.request('inside', time(10), time(11))
        self.request('pending', time(10, 30), time(11, 30), 'pending')
        self.request('ended', time(9), time(10))
        self.request('later', time(11), time(12))
        self.request('completed', time(10), time(11), 'completed')
        self.request('foreign', time(10), time(11), faculty=self.other)
        self.request('no-time', None, None)
        with self.assertNumQueries(2):
            result = get_hourly_availability_snapshot('CCS')
        self.assertEqual(result['available_names'], ['Lance'])
        self.assertEqual(result['approved_count'], 2)
        self.assertEqual(result['pending_count'], 1)
        with patch('apps.depthead.services.analytics.timezone.now', return_value=self.now.replace(hour=11)):
            self.assertEqual(get_hourly_availability_snapshot('CCS')['approved_count'], 1)

    def test_api_cannot_select_another_college_or_role(self):
        url = reverse('depthead:hourly_availability')
        result = self.client.get(url, {'college': 'CBA'})
        self.assertEqual(result.json()['available_names'], ['Lance'])
        self.assertIn('no-store', result['Cache-Control'])
        self.client.force_login(self.student)
        self.assertEqual(self.client.get(url).status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.get(url).status_code, 302)

    def test_week_status_and_approval_boundaries(self):
        week = current_week_period()
        self.assertEqual((week.start_date, week.end_date), (date(2026, 10, 5), date(2026, 10, 11)))
        monday = week.start_datetime
        StatusHistory.objects.create(history_id='carry', faculty=self.faculty,
                                     status='available', changed_at=monday-timedelta(hours=1))
        StatusHistory.objects.create(history_id='change', faculty=self.faculty,
                                     status='busy', changed_at=monday+timedelta(hours=5, minutes=15))
        StatusHistory.objects.create(history_id='future', faculty=self.faculty,
                                     status='available', changed_at=monday+timedelta(days=1))
        future = self.request('future-appointment', time(10), time(11), day=date(2026, 10, 19))
        ConsultationRequest.objects.filter(pk=future.pk).update(
            approved_at=monday+timedelta(hours=2), requested_at=monday)
        self.request('weekly-completed', time(10), time(11), 'completed')
        self.request('weekly-pending', time(10), time(11), 'pending', day=date(2026, 10, 11))
        self.request('outside', time(10), time(11), 'completed', day=date(2026, 10, 12))
        result = get_faculty_trends('CCS', week.start_date, week.end_date, status_period=True)['items'][0]
        self.assertEqual(result['availability_rate_percent'], 50)
        self.assertEqual(result['updates_per_day'], 2.3)
        self.assertEqual(result['average_approval_response_hours'], 2)
        self.assertEqual(result['completion_rate_percent'], 50)
        self.assertEqual(datetime.fromisoformat(result['last_update_at']), monday+timedelta(hours=5, minutes=15))

    def test_pages_show_week_and_plain_context(self):
        peak = self.client.get(reverse('depthead:peak_analytics'))
        self.assertEqual(peak.context['reporting_start'], date(2026, 10, 5))
        self.assertEqual(peak.context['reporting_end'], date(2026, 10, 11))
        self.assertContains(peak, 'Faculty availability and consultations')
        self.assertNotContains(peak, 'Capacity Analytics')
        trends = self.client.get(reverse('depthead:faculty_trends'))
        self.assertContains(trends, 'No updates this week')
        self.assertNotContains(trends, 'Last 7 days')
        self.assertNotContains(trends, 'Tiny positive rates')
