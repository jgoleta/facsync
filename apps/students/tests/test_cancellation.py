from datetime import date, time
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.faculty.models import ConsultationRequest, FacultyProfile, GoogleCalendarConnection
from apps.faculty.services.google_calendar import GoogleCalendarError


class CancellationTests(TestCase):
    def setUp(self):
        self.student = get_user_model().objects.create_user(username='cancel-student', role='student')
        self.teacher = get_user_model().objects.create_user(username='cancel-teacher', role='faculty')
        self.faculty = FacultyProfile.objects.create(user=self.teacher, faculty_id='cancel-faculty', college_id='CCS')
        self.consultation = ConsultationRequest.objects.create(
            request_id='cancel-test', user=self.student, faculty=self.faculty,
            date=date(2026, 10, 2), start_time=time(10), end_time=time(11), status='approved',
        )
        self.student_url = reverse('students:api_request_consultation_cancellation', args=['cancel-test'])
        self.faculty_url = reverse('faculty:api_consultation', args=['cancel-test'])

    def request_cancellation(self):
        self.client.force_login(self.student)
        response = self.client.post(self.student_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], 'cancellation_requested')

    def decide(self, status):
        self.client.force_login(self.teacher)
        return self.client.post(self.faculty_url, {'status': status}, content_type='application/json')

    def test_acceptance_updates_student_and_removes_faculty_card(self):
        self.request_cancellation()
        self.assertEqual(self.decide('cancelled').status_code, 200)
        self.consultation.refresh_from_db()
        self.assertEqual(self.consultation.status, 'cancelled')
        self.assertNotContains(self.client.get(reverse('faculty:dashboard')), 'data-request-id="cancel-test"')
        self.client.force_login(self.student)
        self.assertContains(self.client.get(reverse('students:consultation_requests')), 'Cancelled')

    def test_faculty_sees_cancellation_decisions_and_consultation_type(self):
        self.request_cancellation()
        self.client.force_login(self.teacher)
        for value, label in [('online', 'Online'), ('face_to_face', 'Face-to-Face')]:
            with self.subTest(consultation_type=value):
                self.consultation.consultation_type = value
                self.consultation.save(update_fields=['consultation_type'])
                response = self.client.get(reverse('faculty:dashboard'))
                self.assertContains(response, 'Cancellation Requested')
                self.assertContains(response, 'Accept Cancellation Request')
                self.assertContains(response, 'Decline Cancellation Request')
                self.assertContains(response, f'<p class="request-type"><strong>Consultation Type:</strong> {label}</p>', html=True)

    @patch('apps.faculty.views.create_consultation_event')
    def test_rejection_keeps_appointment_and_restores_student_button(self, create_event):
        self.request_cancellation()
        self.assertEqual(self.decide('approved').status_code, 200)
        create_event.assert_not_called()
        self.client.force_login(self.student)
        self.assertContains(self.client.get(reverse('students:consultation_requests')), 'Request Cancellation')

    @patch('apps.faculty.views.delete_consultation_event', side_effect=GoogleCalendarError('offline'))
    def test_failed_calendar_removal_preserves_request_for_retry(self, delete_event):
        GoogleCalendarConnection.objects.create(user=self.teacher, access_token='test', calendar_id='primary')
        self.consultation.google_event_id = 'event-test'
        self.consultation.google_calendar_id = 'primary'
        self.consultation.save()
        self.request_cancellation()
        self.assertEqual(self.decide('cancelled').status_code, 502)
        self.consultation.refresh_from_db()
        self.assertEqual(self.consultation.status, 'cancellation_requested')
        self.assertEqual(self.consultation.google_event_id, 'event-test')

    def test_student_cannot_accept_or_cancel_another_students_request(self):
        self.request_cancellation()
        self.assertEqual(self.client.post(self.faculty_url, {'status': 'cancelled'}, content_type='application/json').status_code, 403)
        other = get_user_model().objects.create_user(username='other-cancel', role='student')
        self.client.force_login(other)
        self.assertEqual(self.client.post(self.student_url).status_code, 404)

    def test_cancelled_request_cannot_be_restored_by_stale_reject_button(self):
        self.request_cancellation()
        self.assertEqual(self.decide('cancelled').status_code, 200)
        self.assertEqual(self.decide('approved').status_code, 409)

    def test_cancellation_pending_remains_on_calendar(self):
        self.request_cancellation()
        response = self.client.get(reverse('students:api_schedule_events'), {'faculty_id': self.faculty.pk})
        self.assertEqual(response.status_code, 200)
        self.assertIn('consultation:cancel-test', [event['id'] for event in response.json()['events']])
