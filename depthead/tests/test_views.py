from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from unittest.mock import patch

from core.models import FacultyInvite
from depthead.models import CollegeAIInsight
from faculty.models import FacultyProfile, ScheduleEvent


class DeptheadViewTests(TestCase):
    def setUp(self):
        self.depthead = get_user_model().objects.create_user(
            username='depthead-view-test',
            password='test-password',
            role='depthead',
            college='CCS',
        )
        self.client.force_login(self.depthead)

    def test_admin_dashboard_renders(self):
        response = self.client.get(reverse('depthead:admin_dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'depthead/adminDashboard.html')

    def test_admin_dashboard_exposes_ai_loading_context(self):
        response = self.client.get(reverse('depthead:admin_dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.context['ai_insights']['available'])
        self.assertEqual(response.context['analytics']['scope']['college_code'], 'CCS')
        self.assertContains(response, reverse('depthead:ai_insights_api'))
        self.assertContains(response, 'Preparing insights')
        self.assertContains(response, 'AI insight category')

    @patch('depthead.views.generate_ai_insights')
    def test_ai_endpoint_returns_success_and_uses_authenticated_college(self, generate_insights):
        generate_insights.return_value = {
            'available': True,
            'error': None,
            'summary': 'Aggregated insight.',
            'key_insights': [],
            'concerns': [],
            'recommendations': [],
            'model': 'gemini-3.5-flash',
            'generated_at': '2026-09-05T10:00:00+08:00',
        }

        response = self.client.get(
            reverse('depthead:ai_insights_api') + '?college=CBA'
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['available'])
        self.assertEqual(response.json()['summary'], 'Aggregated insight.')
        analytics_sent = generate_insights.call_args.args[0]
        self.assertEqual(analytics_sent['scope']['college_code'], self.depthead.college)

    @patch('depthead.views.generate_ai_insights')
    def test_ai_endpoint_returns_safe_failure(self, generate_insights):
        generate_insights.return_value = {
            'available': False,
            'error': 'AI insights are temporarily unavailable.',
            'summary': None,
            'key_insights': [],
            'concerns': [],
            'recommendations': [],
            'model': 'gemini-3.5-flash',
            'generated_at': None,
        }

        response = self.client.get(reverse('depthead:ai_insights_api'))

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()['available'])
        self.assertEqual(
            response.json()['error'],
            'AI insights are temporarily unavailable.',
        )

    @patch('depthead.views.generate_ai_insights')
    @patch('depthead.views.get_college_analytics')
    def test_ai_endpoint_returns_fresh_database_result_without_generation(
        self,
        get_analytics,
        generate_insights,
    ):
        generated_at = timezone.now()
        CollegeAIInsight.objects.create(
            college_code='CCS',
            analytics_hash='a' * 64,
            insights={
                'available': True,
                'error': None,
                'summary': 'Stored weekly summary.',
                'key_insights': [],
                'concerns': [],
                'recommendations': [],
                'model': 'gemini-3.5-flash',
                'generated_at': generated_at.isoformat(),
            },
            model_name='gemini-3.5-flash',
            generated_at=generated_at,
            refresh_after=generated_at + timedelta(days=7),
        )

        response = self.client.get(reverse('depthead:ai_insights_api'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['summary'], 'Stored weekly summary.')
        self.assertEqual(response.json()['source'], 'database')
        get_analytics.assert_not_called()
        generate_insights.assert_not_called()

    @patch('depthead.views.generate_ai_insights')
    def test_non_depthead_cannot_access_ai_endpoint(self, generate_insights):
        student = get_user_model().objects.create_user(
            username='student-ai-endpoint-test',
            password='test-password',
            role='student',
            college='CCS',
        )
        self.client.force_login(student)

        response = self.client.get(reverse('depthead:ai_insights_api'))

        self.assertEqual(response.status_code, 403)
        generate_insights.assert_not_called()

    def test_admin_faculty_renders(self):
        user = get_user_model().objects.create_user(
            username='depthead-admin-faculty-route-test',
            password='test-password',
            role='depthead',
            college='CCS',
        )
        get_user_model().objects.create_user(
            username='faculty-without-profile-test',
            password='test-password',
            role='faculty',
            account_status='active',
            college='CCS',
        )
        self.client.force_login(user)
        response = self.client.get(reverse('depthead:admin_faculty'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'depthead/adminFaculty.html')

    def test_depthead_can_upload_schedule_for_same_college_faculty(self):
        depthead = get_user_model().objects.create_user(
            username='depthead-schedule-upload-test',
            password='test-password',
            role='depthead',
            college='CCS',
        )
        faculty_user = get_user_model().objects.create_user(
            username='faculty-depthead-upload-test',
            password='test-password',
            role='faculty',
            college='CCS',
        )
        faculty = FacultyProfile.objects.create(
            faculty_id='faculty-depthead-upload-test',
            user=faculty_user,
            college_id='CCS',
        )
        self.client.force_login(depthead)
        upload = SimpleUploadedFile(
            'schedule.csv',
            b'event_title,short_description,room_location,recurring_day,start_month,end_month,start_time,end_time,status_type\n'
            b'College class,Class schedule,Room 204,Monday,8,5,10:30,12:00,Busy\n',
            content_type='text/csv',
        )

        response = self.client.post(
            reverse('depthead:upload_faculty_schedule', args=[faculty.faculty_id]),
            {'file': upload},
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()['added_count'], 1)
        self.assertTrue(faculty.schedule_events.filter(title='College class').exists())

        preview_response = self.client.get(
            reverse('depthead:view_faculty_schedule_preview', args=[faculty.faculty_id]),
        )
        self.assertEqual(preview_response.status_code, 200)
        self.assertEqual(len(preview_response.json()['preview']), 1)

        delete_response = self.client.post(
            reverse('depthead:delete_faculty_schedule', args=[faculty.faculty_id]),
        )
        self.assertEqual(delete_response.status_code, 200)
        self.assertTrue(delete_response.json()['success'])
        self.assertEqual(faculty.schedule_events.count(), 0)

    def test_depthead_can_create_faculty_invite_as_ajax(self):
        depthead = get_user_model().objects.create_user(
            username='depthead-invite-test',
            password='test-password',
            role='depthead',
            college='CCS',
        )
        self.client.force_login(depthead)

        response = self.client.post(
            reverse('depthead:invite_faculty'),
            {'email': 'new-faculty@example.com'},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.json()['success'])
        self.assertTrue(FacultyInvite.objects.filter(
            email='new-faculty@example.com',
            college='CCS',
            invited_by=depthead,
        ).exists())

        invite = FacultyInvite.objects.get(email='new-faculty@example.com')
        invite.used = True
        invite.save(update_fields=['used'])

        reuse_response = self.client.post(
            reverse('depthead:invite_faculty'),
            {'email': 'new-faculty@example.com'},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        self.assertEqual(reuse_response.status_code, 201)
        invite.refresh_from_db()
        self.assertFalse(invite.used)

    def test_student_behavior_renders(self):
        response = self.client.get(reverse('depthead:student_behavior'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'depthead/studentBehavior.html')

    def test_faculty_monitoring_renders(self):
        response = self.client.get(reverse('depthead:faculty_monitoring'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'depthead/facultyMonitoring.html')

    def test_college_settings_renders(self):
        response = self.client.get(reverse('depthead:college_settings'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'depthead/collegeSettings.html')

    def test_peak_analytics_renders(self):
        response = self.client.get(reverse('depthead:peak_analytics'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'depthead/peakAnalytics.html')

    def test_faculty_trends_renders(self):
        response = self.client.get(reverse('depthead:faculty_trends'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'depthead/facultyTrends.html')
