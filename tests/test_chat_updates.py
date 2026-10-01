from datetime import time, timedelta
from unittest.mock import patch
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from django.db import connection
from django.test.utils import CaptureQueriesContext
from apps.core.models import User, CollegeAnnouncement, OfficeClosure
from apps.core.department_updates import UPDATE_QUESTIONS
from apps.faculty.models import FacultyProfile, ConsultationRequest
from apps.faculty.services.consultation_browser import QUESTIONS
from apps.depthead.services.analytics_browser import ANALYTICS_QUESTIONS


class ChatUpdatesTests(TestCase):
    def setUp(self):
        self.head = User.objects.create(username='head-chat', role='depthead', college='CCS')
        self.student = User.objects.create(username='student-chat', role='student', college='CCS')
        self.owner = User.objects.create(username='faculty-chat', role='faculty', college='CCS', account_status='active')
        self.faculty = FacultyProfile.objects.create(user=self.owner, faculty_id='owner-chat', college_id='CCS')
        self.url = reverse('faculty:consultation_browser_api')
        self.client.force_login(self.owner)
        now = timezone.now()
        for college in ('CCS', 'CBA'):
            for audience in ('faculty', 'students', 'both'):
                CollegeAnnouncement.objects.create(college=college, audience=audience,
                    message=f'{college}-{audience}-notice', expiry=now+timedelta(days=2), posted_by=self.head)
        CollegeAnnouncement.objects.create(college='CCS', message='EXPIRED-NOTICE', expiry=now-timedelta(days=1), posted_by=self.head)
        self.own = ConsultationRequest.objects.create(request_id='own-chat', faculty=self.faculty, user=self.student,
            date=timezone.localdate(), start_time=time(9), end_time=time(10), status='completed', agenda='grade_consultation')

    def test_announcement_audiences_and_college_for_all_roles(self):
        for user, endpoint, visible, excluded in (
            (self.owner, self.url, 'faculty', 'students'),
            (self.student, reverse('students:availability_browser_api'), 'students', 'faculty'),
            (self.head, reverse('depthead:analytics_browser_api'), 'faculty', None),
        ):
            self.client.force_login(user)
            response = self.client.get(endpoint, {'metric':'active_announcements', 'college':'CBA', 'role':'depthead', 'audience':'both'})
            self.assertEqual(response.status_code, 200)
            text = str(response.json())
            self.assertIn(f'CCS-{visible}-notice', text)
            self.assertIn('CCS-both-notice', text)
            if excluded:
                self.assertNotIn(f'CCS-{excluded}-notice', text)
            else:
                self.assertIn('CCS-students-notice', text)
            self.assertNotIn('CBA-', text)
            self.assertNotIn('EXPIRED-NOTICE', text)
            self.assertIn('Expires:', text)
            self.assertIn('Posted:', text)
            self.assertIn('no-store', response['Cache-Control'])

    def test_faculty_metrics_ignore_other_faculty_even_in_same_college(self):
        metrics = [key for key in QUESTIONS if key not in UPDATE_QUESTIONS]
        original = {key:self.client.get(self.url, {'metric':key}).json() for key in metrics}
        for college in ('CCS', 'CBA'):
            user = User.objects.create(username=f'other-{college}', role='faculty', college=college)
            profile = FacultyProfile.objects.create(user=user, faculty_id=f'other-{college}', college_id=college)
            student = User.objects.create(username=f'PRIVATE-STUDENT-{college}', role='student', college=college)
            for i in range(3):
                ConsultationRequest.objects.create(request_id=f'other-{college}-{i}', faculty=profile, user=student,
                    date=timezone.localdate(), start_time=time(15), end_time=time(16), status='completed', agenda='project_consultation')
        with patch('apps.faculty.views.refresh_faculty_status') as refresh:
            for metric in metrics:
                with CaptureQueriesContext(connection) as queries:
                    response = self.client.get(self.url, {'metric':metric, 'faculty_id':'other-CCS', 'college':'CBA'})
                self.assertEqual(response.json(), original[metric])
                self.assertNotIn('PRIVATE-STUDENT', str(response.json()))
                for query in queries:
                    self.assertNotRegex(query['sql'].upper(), r'^\s*(INSERT|UPDATE|DELETE)\b')
            refresh.assert_not_called()
        self.assertIn('1 submitted requests', str(original['peak_request_period']['lines']))
        self.assertIn('student-chat: 1 requests', str(original['student_frequency']['lines']))

    def test_faculty_role_method_and_metric_guards(self):
        for metric in ('faculty_load', 'completion_rates', 'daily_faculty', 'available_now', 'unknown', ''):
            self.assertEqual(self.client.get(self.url, {'metric':metric}).status_code, 400)
        self.assertEqual(self.client.post(self.url).status_code, 405)
        for user in (self.student, self.head):
            self.client.force_login(user)
            self.assertEqual(self.client.get(self.url, {'metric':'peak_day'}).status_code, 403)
        admin = User.objects.create(username='admin-chat', role='superadmin')
        self.client.force_login(admin)
        self.assertEqual(self.client.get(self.url, {'metric':'peak_day'}).status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.get(self.url, {'metric':'peak_day'}).status_code, 302)

    def test_closure_matches_saved_flag_and_repeated_reads(self):
        OfficeClosure.objects.create(college='CBA', is_closed=True, reason='PRIVATE-CLOSURE')
        closure = OfficeClosure.objects.create(college='CCS', is_closed=True, reason='Meeting',
            closure_start=timezone.localdate()-timedelta(days=3), closure_end=timezone.localdate()-timedelta(days=2))
        for user, url in ((self.owner,self.url),(self.student,reverse('students:availability_browser_api')),
                          (self.head,reverse('depthead:analytics_browser_api'))):
            self.client.force_login(user)
            response = self.client.get(url, {'metric':'college_closure','college':'CBA'})
            self.assertIn('College status: Closed', response.json()['lines'])
            self.assertNotIn('PRIVATE-CLOSURE', str(response.json()))
        self.client.force_login(self.owner)
        closure.is_closed = False
        closure.save()
        self.assertIn('College status: Open', self.client.get(self.url, {'metric':'college_closure'}).json()['lines'])
        closure.delete()
        self.assertIn('No closure record is configured.', self.client.get(self.url, {'metric':'college_closure'}).json()['lines'])

    def test_empty_and_missing_profile(self):
        ConsultationRequest.objects.all().delete()
        for metric in QUESTIONS:
            self.assertEqual(self.client.get(self.url, {'metric':metric}).status_code, 200)
        self.faculty.college_id = ''
        self.faculty.save()
        self.assertEqual(self.client.get(self.url, {'metric':'active_announcements','college':'CCS'}).status_code, 400)
        self.faculty.delete()
        self.assertEqual(self.client.get(self.url, {'metric':'peak_day'}).status_code, 400)

    def test_order_topics_and_dashboard_widget(self):
        groups = list(dict.fromkeys(group for group, question in ANALYTICS_QUESTIONS.values()))
        self.assertEqual(groups, ['Schedules','Consultations','Faculty','Students','Department updates'])
        self.client.force_login(self.head)
        response = self.client.get(reverse('depthead:analytics_browser_api'), {'metric':'consultation_topics'})
        self.assertEqual(response.status_code, 200)
        self.assertIn('1 requests (100.00%)', str(response.json()['lines']))
        self.client.force_login(self.owner)
        with patch('apps.faculty.views.refresh_faculty_status'):
            response = self.client.get(reverse('faculty:dashboard'))
        self.assertContains(response, self.url)
        self.assertContains(response, 'Your consultations')
        self.assertContains(response, 'Department updates')
        self.assertNotContains(response, 'data-metric="completion_rates"')
