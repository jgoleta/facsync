from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile

from core.models import FacultyInvite
from faculty.models import FacultyProfile, ScheduleEvent


class DeptheadViewTests(TestCase):
    def test_admin_dashboard_renders(self):
        response = self.client.get(reverse('depthead:admin_dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'depthead/adminDashboard.html')

    def test_admin_faculty_renders(self):
        user = get_user_model().objects.create_user(
            username='depthead-admin-faculty-route-test',
            password='test-password',
            role='depthead',
            department='CCS',
        )
        get_user_model().objects.create_user(
            username='faculty-without-profile-test',
            password='test-password',
            role='faculty',
            account_status='active',
            department='CCS',
        )
        self.client.force_login(user)
        response = self.client.get(reverse('depthead:admin_faculty'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'depthead/adminFaculty.html')

    def test_depthead_can_upload_schedule_for_same_department_faculty(self):
        depthead = get_user_model().objects.create_user(
            username='depthead-schedule-upload-test',
            password='test-password',
            role='depthead',
            department='CCS',
        )
        faculty_user = get_user_model().objects.create_user(
            username='faculty-depthead-upload-test',
            password='test-password',
            role='faculty',
            department='CCS',
        )
        faculty = FacultyProfile.objects.create(
            faculty_id='faculty-depthead-upload-test',
            user=faculty_user,
            department_id='CCS',
        )
        self.client.force_login(depthead)
        upload = SimpleUploadedFile(
            'schedule.csv',
            b'event_title,short_description,room_location,recurring_day,start_month,end_month,start_time,end_time,status_type\n'
            b'Department class,Class schedule,Room 204,Monday,8,5,10:30,12:00,Busy\n',
            content_type='text/csv',
        )

        response = self.client.post(
            reverse('depthead:upload_faculty_schedule', args=[faculty.faculty_id]),
            {'file': upload},
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()['added_count'], 1)
        self.assertTrue(faculty.schedule_events.filter(title='Department class').exists())

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
            department='CCS',
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
            department='CCS',
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

    def test_department_settings_renders(self):
        response = self.client.get(reverse('depthead:department_settings'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'depthead/departmentSettings.html')

    def test_peak_analytics_renders(self):
        response = self.client.get(reverse('depthead:peak_analytics'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'depthead/peakAnalytics.html')

    def test_faculty_trends_renders(self):
        response = self.client.get(reverse('depthead:faculty_trends'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'depthead/facultyTrends.html')
