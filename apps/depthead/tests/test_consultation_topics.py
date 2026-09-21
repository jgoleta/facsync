from datetime import date, datetime, timezone
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse

from apps.core.models import User
from apps.faculty.models import ConsultationRequest, FacultyProfile
from apps.depthead.services.analytics_display import consultation_topics_display


class ConsultationTopicsTests(TestCase):
    def setUp(self):
        head = User.objects.create(username='topics-head', role='depthead', college='CCS')
        self.student = User.objects.create(username='topics-student', role='student', college='CBA')
        self.faculty = {}
        for college in ('CCS', 'CBA'):
            user = User.objects.create(username=f'topics-{college}', role='faculty', college=college)
            self.faculty[college] = FacultyProfile.objects.create(
                faculty_id=f'topics-{college}', user=user, college_id=college)
        self.client.force_login(head)

    def page(self):
        with patch('apps.depthead.services.analytics.timezone.now',
                   return_value=datetime(2026, 9, 21, 4, tzinfo=timezone.utc)):
            return self.client.get(reverse('depthead:student_behavior'))

    def test_empty_state(self):
        response = self.page()
        self.assertContains(response, 'No consultation requests in this period.')
        self.assertEqual(response.context['consultation_topics'], [])

    def test_all_statuses_college_scope_and_scheduled_boundaries(self):
        for i, (status, _) in enumerate(ConsultationRequest.STATUS_CHOICES):
            ConsultationRequest.objects.create(
                request_id=f'topic-{i}', user=self.student, faculty=self.faculty['CCS'],
                status=status, agenda=('general_concern' if i < 3 else ''),
                date=date(2026, 4, 1) if i < 3 else date(2026, 9, 21))
        for i, (college, scheduled) in enumerate((
            ('CBA', date(2026, 9, 21)), ('CCS', date(2026, 3, 31)),
            ('CCS', date(2026, 9, 22)),
        )):
            ConsultationRequest.objects.create(
                request_id=f'excluded-{i}', user=self.student, faculty=self.faculty[college],
                agenda='project_consultation', date=scheduled)
        # Submission timestamps deliberately fall outside the selected period.
        ConsultationRequest.objects.update(requested_at=datetime(2025, 1, 1, tzinfo=timezone.utc))
        with self.assertNumQueries(10):
            response = self.page()
        rows = response.context['consultation_topics']
        self.assertEqual(rows[:2], [
            {'label': 'General Concern / Talk', 'count': 3, 'percentage': 60.0},
            {'label': 'Unspecified', 'count': 2, 'percentage': 40.0},
        ])
        self.assertEqual(sum(row['count'] for row in rows), 5)
        self.assertContains(response, '60.00%')

    def test_presentation_is_query_free_and_preserves_unknown_values(self):
        with self.assertNumQueries(0):
            rows = consultation_topics_display({'total_records': 5, 'agenda_distribution': {
                '': 1, '  ': 1, None: 1, 'academic_advising': 1, 'retired_topic': 1,
            }})
        self.assertEqual(rows[0], {'label': 'Unspecified', 'count': 3, 'percentage': 60.0})
        self.assertEqual(rows[1]['label'], 'Academic Advising')
        self.assertEqual(rows[2]['label'], 'Unrecognized topic (retired_topic)')
        self.assertEqual(sum(row['count'] for row in rows), 5)
