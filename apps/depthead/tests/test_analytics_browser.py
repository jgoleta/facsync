from unittest.mock import patch
from django.test import TestCase
from django.urls import reverse
from apps.core.models import User
from apps.faculty.models import FacultyProfile, ConsultationRequest
from apps.depthead.services.analytics_browser import ANALYTICS_QUESTIONS


class AnalyticsBrowserTests(TestCase):
    def setUp(self):
        self.head = User.objects.create(username='browser-head', role='depthead', college='CCS')
        self.client.force_login(self.head)
        self.url = reverse('depthead:analytics_browser_api')

    def test_all_questions_return_scoped_answers_without_ai(self):
        with patch('apps.depthead.views.generate_ai_insights') as ai:
            for metric in ANALYTICS_QUESTIONS:
                with self.subTest(metric=metric):
                    response = self.client.get(self.url, {'metric': metric})
                    self.assertEqual(response.status_code, 200)
                    self.assertTrue(response.json()['lines'])
                    self.assertIn('no-store', response['Cache-Control'])
            ai.assert_not_called()

    def test_scope_ignores_client_college(self):
        for college in ('CCS', 'CBA'):
            user = User.objects.create(username=college, role='faculty', college=college)
            faculty = FacultyProfile.objects.create(faculty_id=college, user=user, college_id=college)
            from django.utils import timezone
            ConsultationRequest.objects.create(request_id=college, faculty=faculty, user=self.head,
                                               date=timezone.localdate(), status='completed')
        response = self.client.get(self.url, {'metric': 'faculty_load', 'college': 'CBA'})
        self.assertEqual(response.json()['lines'], ['CCS: 1 requests'])

    def test_validation_and_access(self):
        self.assertEqual(self.client.get(self.url, {'metric': 'unknown'}).status_code, 400)
        self.assertEqual(self.client.post(self.url).status_code, 405)
        self.head.college = ''
        self.head.save()
        self.assertEqual(self.client.get(self.url, {'metric': 'capacity'}).status_code, 400)
        self.head.role = 'student'
        self.head.save()
        self.assertEqual(self.client.get(self.url, {'metric': 'capacity'}).status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.get(self.url, {'metric': 'capacity'}).status_code, 302)

    @patch('apps.depthead.services.analytics_browser.get_schedule_availability')
    def test_repeated_fetch_reuses_schedule_service_each_time(self, schedules):
        schedules.return_value = {'week_start': '2026-09-14', 'week_end': '2026-09-20',
                                 'timezone': 'Asia/Manila', 'faculty_count': 0, 'rows': []}
        for _ in range(2):
            self.assertEqual(self.client.get(self.url, {'metric': 'daily_availability'}).status_code, 200)
        self.assertEqual(schedules.call_count, 2)
        schedules.assert_called_with('CCS')

    def test_capacity_honestly_unavailable(self):
        answer = self.client.get(self.url, {'metric': 'capacity'}).json()
        self.assertIn('not currently measurable', answer['lines'][0])

    @patch('apps.depthead.views.analytics_browser_answer', side_effect=RuntimeError('offline'))
    def test_error_returns_friendly_json(self, answer):
        with self.assertLogs('apps.depthead.views', level='ERROR'):
            response = self.client.get(self.url, {'metric': 'capacity'})
        self.assertEqual(response.status_code, 500)
        self.assertIn("couldn't load", response.json()['error'])

    def test_widget_only_on_overview(self):
        response = self.client.get(reverse('depthead:admin_dashboard'))
        self.assertContains(response, 'id="analytics-browser"', count=1)
        self.assertContains(response, 'data-metric=', count=12)
        for page in ('peak_analytics', 'faculty_trends', 'student_behavior'):
            response = self.client.get(reverse(f'depthead:{page}'))
            self.assertEqual(response.status_code, 200)
            self.assertNotContains(response, 'id="analytics-browser"')
            self.assertNotContains(response, 'analytics_browser.js')
