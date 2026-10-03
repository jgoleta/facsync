from datetime import time
from unittest.mock import patch
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from django.db import connection
from django.test.utils import CaptureQueriesContext
from apps.core.models import User, OfficeClosure
from apps.faculty.models import FacultyProfile, ScheduleEvent, StatusHistory
from apps.students.availability_browser import QUESTIONS
from apps.core.department_updates import UPDATE_QUESTIONS
from apps.depthead.services.analytics_browser import ANALYTICS_QUESTIONS


class AvailabilityBrowserTests(TestCase):
    def setUp(self):
        self.student = User.objects.create(username='student-browser', role='student', college='CCS')
        self.client.force_login(self.student)
        self.url = reverse('students:availability_browser_api')
        self.faculty = []
        for name, college in [('local-one', 'CCS'), ('local-two', 'CCS'), ('PRIVATE-OTHER-COLLEGE', 'CBA')]:
            user = User.objects.create(username=name, role='faculty', college=college, account_status='active')
            profile = FacultyProfile.objects.create(user=user, faculty_id=name, college_id=college, current_status='available')
            ScheduleEvent.objects.create(faculty=profile, title='PRIVATE-EVENT-TITLE', description='PRIVATE-DESCRIPTION',
                                         date=timezone.localdate(), start_time=time(8), end_time=time(9), event_type='busy')
            self.faculty.append(profile)

    def test_every_answer_scoped_and_read_only(self):
        before = list(FacultyProfile.objects.values_list('pk', 'current_status', 'status_updated_at'))
        history = StatusHistory.objects.count()
        with patch('apps.students.views.refresh_faculty_status') as refresh, patch('apps.depthead.services.analytics_browser.analytics_browser_answer') as admin:
            for metric in QUESTIONS:
                with CaptureQueriesContext(connection) as queries:
                    response = self.client.get(self.url, {'metric': metric, 'college': 'CBA'})
                for query in queries:
                    self.assertNotRegex(query['sql'].upper(), r'^\s*(INSERT|UPDATE|DELETE)\b')
                self.assertEqual(response.status_code, 200)
                self.assertIn('no-store', response['Cache-Control'])
                text = response.content.decode()
                for private in ('PRIVATE-OTHER-COLLEGE', 'PRIVATE-EVENT-TITLE', 'PRIVATE-DESCRIPTION', 'completion_rate', 'response_time'):
                    self.assertNotIn(private, text)
                self.assertEqual(set(response.json()), {'period', 'lines', 'note', 'source_url', 'source_label', 'presentation'})
            refresh.assert_not_called()
            admin.assert_not_called()
        self.assertEqual(before, list(FacultyProfile.objects.values_list('pk', 'current_status', 'status_updated_at')))
        self.assertEqual(history, StatusHistory.objects.count())

    def test_rejects_all_admin_questions_and_unknown_metric(self):
        for metric in [key for key in ANALYTICS_QUESTIONS if key not in UPDATE_QUESTIONS] + ['unknown', '', '__dict__']:
            self.assertEqual(self.client.get(self.url, {'metric': metric}).status_code, 400)
        self.assertEqual(self.client.get(reverse('depthead:analytics_browser_api'), {'metric':'faculty_load'}).status_code, 403)

    def test_roles_missing_college_and_method(self):
        self.assertEqual(self.client.post(self.url).status_code, 405)
        self.student.college = ''
        self.student.save()
        self.assertEqual(self.client.get(self.url, {'metric':'available_now', 'college':'CCS'}).status_code, 400)
        for role in ('faculty', 'depthead', 'superadmin'):
            self.student.role = role
            self.student.save()
            self.assertEqual(self.client.get(self.url, {'metric':'available_now'}).status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.get(self.url, {'metric':'available_now'}).status_code, 302)

    def test_ties_and_repeated_requests(self):
        for _ in range(2):
            data = self.client.get(self.url, {'metric':'today_open'}).json()
            self.assertIn('local-one', str(data['lines']))
            self.assertIn('local-two', str(data['lines']))
        data = self.client.get(self.url, {'metric':'best_day'}).json()
        self.assertEqual(len(data['lines']), 7)

    def test_closed_college_and_empty_results(self):
        OfficeClosure.objects.create(college='CCS', is_closed=True)
        data = self.client.get(self.url, {'metric':'available_now'}).json()
        self.assertIn('closed', str(data['lines']))
        self.assertNotIn('local-one', str(data['lines']))
        self.assertIn('closed', self.client.get(self.url, {'metric':'today_open'}).json()['note'])
        OfficeClosure.objects.all().delete()
        User.objects.filter(role='faculty', college='CCS').update(account_status='deactivated')
        for metric in QUESTIONS:
            data = self.client.get(self.url, {'metric':metric}).json()
            self.assertNotIn('local-one', str(data))
            self.assertTrue(data['lines'])

    def test_only_dashboard_contains_widget(self):
        with patch('apps.students.views.refresh_faculty_status'):
            response = self.client.get(reverse('students:dashboard'))
        self.assertContains(response, self.url)
        for question in QUESTIONS.values():
            self.assertContains(response, question)
        self.assertNotContains(response, 'data-metric="completion_rates"')
        self.assertNotContains(self.client.get(reverse('students:home')), 'id="analytics-browser"')
