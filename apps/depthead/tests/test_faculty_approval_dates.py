from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo

from django.test import TestCase

from apps.core.models import User
from apps.faculty.models import FacultyProfile, ConsultationRequest
from apps.depthead.services.analytics import get_faculty_trends


class FacultyApprovalDatesTests(TestCase):
    def test_approval_window_is_independent_of_completion_window(self):
        tz = ZoneInfo('Asia/Manila')
        owner = User.objects.create_user(username='approval-faculty', role='faculty', account_status='active')
        faculty = FacultyProfile.objects.create(user=owner, faculty_id='approval-faculty', college_id='CCS')
        student = User.objects.create_user(username='approval-student')
        start = datetime(2026, 10, 1, tzinfo=tz)
        end = datetime(2026, 10, 6, tzinfo=tz)

        def add(key, approved, hours, scheduled=date(2026, 10, 10), status='approved', profile=faculty):
            row = ConsultationRequest.objects.create(request_id=key, user=student, faculty=profile,
                date=scheduled, status=status, approved_at=approved)
            ConsultationRequest.objects.filter(pk=row.pk).update(requested_at=approved - timedelta(hours=hours))

        add('future-first', start, 2)
        add('future-last', end - timedelta(microseconds=1), 6)
        add('too-old', start - timedelta(microseconds=1), 50, scheduled=date(2026, 10, 2), status='completed')
        add('too-new', end, 50)
        add('invalid-duration', start + timedelta(hours=3), -1)
        other_user = User.objects.create_user(username='other-approval-faculty', role='faculty', account_status='active')
        other = FacultyProfile.objects.create(user=other_user, faculty_id='other-approval', college_id='CBA')
        add('other-college', start, 100, profile=other)
        ConsultationRequest.objects.create(request_id='missing-timestamp', user=student, faculty=faculty,
            date=date(2026, 10, 3), status='approved')
        data = get_faculty_trends('CCS', date(2026, 10, 1), date(2026, 10, 5))
        row = data['items'][0]
        self.assertEqual(row['average_approval_response_hours'], 4.0)
        self.assertEqual(row['completion_rate_percent'], 50.0)
