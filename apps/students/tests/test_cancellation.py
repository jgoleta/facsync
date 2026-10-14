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
        self.assertEqual(response.json()['status'], 'cancelled')

    def decide(self, status):
        self.client.force_login(self.teacher)
        return self.client.post(self.faculty_url, {'status': status}, content_type='application/json')

    def test_student_cancellation_removes_faculty_card_immediately(self):
        self.request_cancellation()
        self.consultation.refresh_from_db()
        self.assertEqual(self.consultation.status, 'cancelled')
        self.assertNotContains(self.client.get(reverse('faculty:dashboard')), 'data-request-id="cancel-test"')
        self.client.force_login(self.student)
        self.assertContains(self.client.get(reverse('students:consultation_requests')), 'Cancelled')

    def test_student_can_cancel_pending_request_immediately(self):
        self.consultation.status = 'pending'
        self.consultation.save(update_fields=['status'])

        self.client.force_login(self.student)
        response = self.client.post(self.student_url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], 'cancelled')
        self.consultation.refresh_from_db()
        self.assertEqual(self.consultation.status, 'cancelled')

    def test_faculty_does_not_see_cancellation_decision_controls(self):
        self.request_cancellation()
        self.client.force_login(self.teacher)
        response = self.client.get(reverse('faculty:dashboard'))
        self.assertNotContains(response, 'data-request-id="cancel-test"')
        self.assertNotContains(response, 'Accept Cancellation Request')
        self.assertNotContains(response, 'Decline Cancellation Request')

    @patch('apps.faculty.views.create_consultation_event')
    def test_cancelled_request_does_not_restore_student_button(self, create_event):
        self.request_cancellation()
        create_event.assert_not_called()
        self.client.force_login(self.student)
        self.assertNotContains(self.client.get(reverse('students:consultation_requests')), 'Cancel Consultation')

    @patch('apps.students.views.delete_consultation_event', side_effect=GoogleCalendarError('offline'))
    def test_failed_calendar_removal_preserves_request_for_retry(self, delete_event):
        GoogleCalendarConnection.objects.create(user=self.teacher, access_token='test', calendar_id='primary')
        self.consultation.google_event_id = 'event-test'
        self.consultation.google_calendar_id = 'primary'
        self.consultation.save()
        self.client.force_login(self.student)
        self.assertEqual(self.client.post(self.student_url).status_code, 502)
        self.consultation.refresh_from_db()
        self.assertEqual(self.consultation.status, 'approved')
        self.assertEqual(self.consultation.google_event_id, 'event-test')

    def test_student_cannot_accept_or_cancel_another_students_request(self):
        self.request_cancellation()
        self.assertEqual(self.client.post(self.faculty_url, {'status': 'cancelled'}, content_type='application/json').status_code, 403)
        other = get_user_model().objects.create_user(username='other-cancel', role='student')
        self.client.force_login(other)
        self.assertEqual(self.client.post(self.student_url).status_code, 404)

    def test_cancelled_request_cannot_be_restored_by_stale_reject_button(self):
        self.request_cancellation()
        self.assertEqual(self.decide('approved').status_code, 409)

    def test_cancelled_consultation_is_removed_from_calendar_feed(self):
        self.request_cancellation()
        response = self.client.get(reverse('students:api_schedule_events'), {'faculty_id': self.faculty.pk})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('consultation:cancel-test', [event['id'] for event in response.json()['events']])
