from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from datetime import date, timedelta
import json

from apps.core.models import CollegeAnnouncement
from apps.faculty.models import ConsultationRequest, FacultyProfile, ScheduleEvent, WalkInQueue


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
            college_id='CCS',
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
            'location': '',
            'status': 'busy',
            'event_type': 'busy',
            'date': '2026-08-20',
            'is_recurring': False,
            'day_of_week': '',
            'start_month': None,
            'end_month': None,
            'recurrence_start_date': None,
            'recurrence_end_date': None,
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

    def test_consultation_booking_requires_and_saves_agenda(self):
        self.client.force_login(self.student)
        payload = {
            'faculty_id': self.faculty.faculty_id,
            'date': date.today().isoformat(),
            'start_time': '10:00',
            'agenda': 'project_consultation',
            'message': 'Review our project plan.',
        }

        response = self.client.post(
            reverse('students:api_consultation_requests'),
            data=json.dumps(payload),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 201)
        consultation = ConsultationRequest.objects.get()
        self.assertEqual(consultation.agenda, 'project_consultation')
        self.assertEqual(response.json()['agenda_label'], 'Project Consultation')

    def test_consultation_booking_rejects_invalid_agenda(self):
        self.client.force_login(self.student)

        response = self.client.post(
            reverse('students:api_consultation_requests'),
            data=json.dumps({
                'faculty_id': self.faculty.faculty_id,
                'date': date.today().isoformat(),
                'start_time': '10:00',
                'agenda': 'not-a-valid-agenda',
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('agenda', response.json()['error'].lower())

    def test_consultation_booking_rejects_faculty_on_leave(self):
        self.faculty.manual_status = 'on_leave'
        self.faculty.manual_status_override = True
        self.faculty.save(update_fields=['manual_status', 'manual_status_override'])
        self.client.force_login(self.student)

        response = self.client.post(
            reverse('students:api_consultation_requests'),
            data=json.dumps({
                'faculty_id': self.faculty.faculty_id,
                'date': date.today().isoformat(),
                'start_time': '10:00',
                'agenda': 'academic_advising',
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 409)
        self.assertIn('on leave', response.json()['error'].lower())
        self.assertFalse(ConsultationRequest.objects.exists())

    def test_schedule_page_disables_booking_when_faculty_is_on_leave(self):
        self.faculty.manual_status = 'on_leave'
        self.faculty.manual_status_override = True
        self.faculty.save(update_fields=['manual_status', 'manual_status_override'])
        self.client.force_login(self.student)

        response = self.client.get(
            reverse('students:view_schedule'),
            {'faculty_id': self.faculty.faculty_id},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Faculty On Leave')
        self.assertContains(response, 'data-faculty-status="on_leave"')

    def test_walk_in_queue_rejects_faculty_on_leave(self):
        self.faculty.manual_status = 'on_leave'
        self.faculty.manual_status_override = True
        self.faculty.walk_ins_enabled = True
        self.faculty.save(update_fields=[
            'manual_status',
            'manual_status_override',
            'walk_ins_enabled',
        ])
        self.client.force_login(self.student)

        response = self.client.post(
            reverse('students:api_join_walk_in_queue'),
            data=json.dumps({'faculty_id': self.faculty.faculty_id}),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 409)
        self.assertIn('on leave', response.json()['error'].lower())
        self.assertFalse(WalkInQueue.objects.exists())

    def test_student_schedule_api_includes_approved_consultation(self):
        ConsultationRequest.objects.create(
            request_id='approved-consultation',
            user=self.student,
            faculty=self.faculty,
            date='2026-08-21',
            start_time='13:00',
            end_time='14:00',
            status='approved',
            student_message='Discuss project feedback.',
        )
        self.client.force_login(self.student)

        response = self.client.get(
            reverse('students:api_schedule_events'),
            {'faculty_id': self.faculty.faculty_id},
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn({
            'id': 'consultation:approved-consultation',
            'request_id': 'approved-consultation',
            'title': 'Consultation with Schedule Faculty',
            'description': 'Discuss project feedback.',
            'location': '',
            'status': 'Consultation',
            'event_type': 'busy',
            'date': '2026-08-21',
            'is_recurring': False,
            'is_consultation': True,
            'day_of_week': '',
            'start_month': None,
            'end_month': None,
            'start_time': '13:00:00',
            'end_time': '14:00:00',
        }, response.json()['events'])

    def test_student_consultation_list_includes_completed_and_excludes_declined_requests(self):
        for request_id, status in (
            ('completed-consultation', 'completed'),
            ('declined-consultation', 'declined'),
        ):
            ConsultationRequest.objects.create(
                request_id=request_id,
                user=self.student,
                faculty=self.faculty,
                date='2026-08-21',
                start_time='13:00',
                end_time='14:00',
                status=status,
            )
        self.client.force_login(self.student)

        response = self.client.get(reverse('students:consultation_requests'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'completed-consultation')
        self.assertNotContains(response, 'declined-consultation')

    def test_student_home_shows_latest_active_announcement_for_student_college(self):
        CollegeAnnouncement.objects.create(
            college='cba',
            message='Announcement for another college',
            expiry=timezone.now() + timedelta(days=2),
            posted_by=self.student,
        )
        CollegeAnnouncement.objects.create(
            college='CCS',
            message='Bring your student ID to the college office.',
            expiry=timezone.now() + timedelta(days=2),
            posted_by=self.student,
        )
        self.student.college = 'ccs'
        self.student.save(update_fields=['college'])
        self.client.force_login(self.student)

        response = self.client.get(reverse('students:home'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Bring your student ID to the college office.')
        self.assertNotContains(response, 'Announcement for another college')
        self.assertNotContains(response, 'Faculty consultation slots are limited this week')
