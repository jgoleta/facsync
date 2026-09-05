from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.faculty.models import ConsultationRequest, FacultyProfile, GoogleCalendarConnection
from apps.faculty.services.google_calendar import GoogleCalendarError


class ConsultationDeletionTests(TestCase):
    def setUp(self):
        self.student = get_user_model().objects.create_user(username='owner', role='student')
        self.faculty_user = get_user_model().objects.create_user(username='teacher', role='faculty')
        self.faculty = FacultyProfile.objects.create(user=self.faculty_user, faculty_id='teacher', college_id='CCS')
        self.request = ConsultationRequest.objects.create(
            request_id='deletion-test', user=self.student, faculty=self.faculty, date='2026-09-10',
        )
        self.url = reverse('students:api_delete_consultation', args=[self.request.pk])
        self.client.force_login(self.student)

    def test_owner_can_delete_each_status_and_request_disappears(self):
        for status, _ in ConsultationRequest.STATUS_CHOICES:
            with self.subTest(status=status):
                self.request.status = status
                self.request.save()
                self.assertEqual(self.client.delete(self.url).status_code, 204)
                self.assertFalse(ConsultationRequest.objects.filter(pk=self.request.pk).exists())
        self.assertNotContains(self.client.get(reverse('students:consultation_requests')), 'deletion-test')
        self.assertEqual(self.client.delete(self.url).status_code, 404)

    def test_other_student_cannot_delete(self):
        other = get_user_model().objects.create_user(username='other', role='student')
        self.client.force_login(other)
        self.assertEqual(self.client.delete(self.url).status_code, 404)
        self.assertTrue(ConsultationRequest.objects.filter(pk=self.request.pk).exists())

    def test_faculty_and_anonymous_cannot_delete(self):
        self.client.force_login(self.faculty_user)
        self.assertEqual(self.client.delete(self.url).status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.delete(self.url).status_code, 302)
        self.assertTrue(ConsultationRequest.objects.filter(pk=self.request.pk).exists())

    def test_get_and_post_cannot_delete(self):
        self.assertEqual(self.client.get(self.url).status_code, 405)
        self.assertEqual(self.client.post(self.url).status_code, 405)
        self.assertTrue(ConsultationRequest.objects.filter(pk=self.request.pk).exists())

    def test_csrf_required_and_page_issues_cookie(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.student)
        self.assertEqual(client.delete(self.url).status_code, 403)
        response = client.get(reverse('students:consultation_requests'))
        self.assertContains(response, 'Delete request')
        token = client.cookies['csrftoken'].value
        self.assertEqual(client.delete(self.url, HTTP_X_CSRFTOKEN=token).status_code, 204)

    def link_calendar(self):
        self.request.google_event_id = 'event-id'
        self.request.google_calendar_id = 'primary'
        self.request.status = 'approved'
        self.request.save()
        return GoogleCalendarConnection.objects.create(
            user=self.faculty_user, google_user_id='teacher', access_token='test', calendar_id='primary',
        )

    @patch('apps.students.views.delete_consultation_event')
    def test_linked_calendar_event_removed(self, delete_event):
        connection = self.link_calendar()
        def check_event_before_deletion(actual_connection, consultation):
            self.assertEqual(actual_connection, connection)
            self.assertEqual(consultation.pk, self.request.pk)
            self.assertEqual(consultation.google_event_id, 'event-id')
            self.assertTrue(ConsultationRequest.objects.filter(pk=consultation.pk).exists())
        delete_event.side_effect = check_event_before_deletion
        self.assertEqual(self.client.delete(self.url).status_code, 204)
        delete_event.assert_called_once()
        self.assertFalse(ConsultationRequest.objects.filter(pk=self.request.pk).exists())

    @patch('apps.students.views.delete_consultation_event', side_effect=GoogleCalendarError('Failed'))
    def test_calendar_failure_preserves_request(self, delete_event):
        self.link_calendar()
        self.assertEqual(self.client.delete(self.url).status_code, 502)
        self.assertTrue(ConsultationRequest.objects.filter(pk=self.request.pk).exists())

    def test_missing_connection_preserves_linked_request(self):
        self.link_calendar().delete()
        self.assertEqual(self.client.delete(self.url).status_code, 409)
        self.assertTrue(ConsultationRequest.objects.filter(pk=self.request.pk).exists())

    def test_different_calendar_preserves_request(self):
        connection = self.link_calendar()
        connection.calendar_id = 'different'
        connection.save()
        self.assertEqual(self.client.delete(self.url).status_code, 409)
        self.assertTrue(ConsultationRequest.objects.filter(pk=self.request.pk).exists())
