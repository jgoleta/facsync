from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta

from core.models import DepartmentAnnouncement
from faculty.models import FacultyProfile, ScheduleEvent


class StudentScheduleTests(TestCase):
    def setUp(self):
        self.student = get_user_model().objects.create_user(
            username='schedule-student',
            password='test-password',
            role='student',
        )
        faculty_user = get_user_model().objects.create_user(
            username='schedule-faculty',
            first_name='Schedule',
            last_name='Faculty',
            password='test-password',
            role='faculty',
        )
        self.faculty = FacultyProfile.objects.create(
            faculty_id='schedule-faculty',
            user=faculty_user,
            department_id='CCS',
        )

    def test_student_schedule_api_returns_faculty_events(self):
        event = ScheduleEvent.objects.create(
            faculty=self.faculty,
            title='Uploaded class',
            description='Visible to students',
            event_type='busy',
            date='2026-08-20',
            start_time='09:00',
            end_time='10:30',
        )
        self.client.force_login(self.student)

        response = self.client.get(
            reverse('students:api_schedule_events'),
            {'faculty_id': self.faculty.faculty_id},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['events'], [{
            'id': event.pk,
            'title': 'Uploaded class',
            'description': 'Visible to students',
            'event_type': 'busy',
            'date': '2026-08-20',
            'start_time': '09:00:00',
            'end_time': '10:30:00',
        }])

    def test_student_schedule_page_includes_selected_faculty(self):
        self.client.force_login(self.student)

        response = self.client.get(
            reverse('students:view_schedule'),
            {'faculty_id': self.faculty.faculty_id},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Schedule Faculty')

    def test_student_home_shows_latest_active_announcement_for_student_department(self):
        DepartmentAnnouncement.objects.create(
            department='cba',
            message='Announcement for another department',
            expiry=timezone.now() + timedelta(days=2),
            posted_by=self.student,
        )
        DepartmentAnnouncement.objects.create(
            department='CCS',
            message='Bring your student ID to the department office.',
            expiry=timezone.now() + timedelta(days=2),
            posted_by=self.student,
        )
        self.student.department = 'ccs'
        self.student.save(update_fields=['department'])
        self.client.force_login(self.student)

        response = self.client.get(reverse('students:home'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Bring your student ID to the department office.')
        self.assertNotContains(response, 'Announcement for another department')
        self.assertNotContains(response, 'Faculty consultation slots are limited this week')
