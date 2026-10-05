from datetime import datetime, timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.test import TestCase

from apps.core.models import User
from apps.faculty.models import FacultyProfile, ConsultationRequest


class StudentFrequencyDatesTests(TestCase):
    def test_submission_dates_all_statuses_college_and_local_boundaries(self):
        tz = ZoneInfo('Asia/Manila')
        now = datetime(2026, 10, 5, 12, tzinfo=tz)
        head = User.objects.create_user(username='head-frequency', role='depthead', college='CCS')
        student = User.objects.create_user(username='student-frequency', role='student')
        owner = User.objects.create_user(username='faculty-frequency', role='faculty')
        faculty = FacultyProfile.objects.create(user=owner, faculty_id='frequency', college_id='CCS')
        self.client.force_login(head)

        def create(pk, submitted, status='pending', appointment=None, teacher=faculty):
            row = ConsultationRequest.objects.create(
                request_id=pk, user=student, faculty=teacher, status=status,
                date=appointment or now.date() + timedelta(days=10),
            )
            ConsultationRequest.objects.filter(pk=row.pk).update(requested_at=submitted)

        # Every status counts immediately even for appointments in the future.
        for index, (status, _) in enumerate(ConsultationRequest.STATUS_CHOICES):
            create(str(index), now, status)
        start = datetime(2026, 5, 1, tzinfo=tz)
        end = datetime(2026, 10, 6, tzinfo=tz)
        create('start-inclusive', start)
        create('end-inside', end - timedelta(microseconds=1))
        create('too-old', start - timedelta(microseconds=1), appointment=now.date())
        create('end-exclusive', end, appointment=now.date())
        other_owner = User.objects.create_user(username='other-frequency', role='faculty')
        other = FacultyProfile.objects.create(user=other_owner, faculty_id='other-frequency', college_id='CBA')
        create('other-college', now, teacher=other)
        with patch('django.utils.timezone.now', return_value=now):
            response = self.client.get('/depthead/student-behavior/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['student_frequency'], [{'name': 'student-frequency', 'count': 8}])
