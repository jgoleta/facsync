from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.faculty.models import ConsultationRequest, FacultyProfile, GoogleCalendarConnection
from apps.faculty.services.google_calendar import (
    GoogleCalendarError, refresh_consultation_meet_link, create_consultation_event,
    update_consultation_event,
)


class MeetRecoveryTests(TestCase):
    def setUp(self):
        teacher = get_user_model().objects.create_user(username='meet-teacher', role='faculty')
        student = get_user_model().objects.create_user(username='meet-student', role='student')
        faculty = FacultyProfile.objects.create(faculty_id='meet-teacher', user=teacher, college_id='CCS')
        self.connection = GoogleCalendarConnection.objects.create(user=teacher, access_token='test')
        self.consultation = ConsultationRequest.objects.create(
            request_id='meet-request', faculty=faculty, user=student, date='2026-09-28',
            mode='online', status='approved', google_event_id='existing-event',
        )
        self.consultation.refresh_from_db()

    @patch('apps.faculty.services.google_calendar.google_request')
    def test_existing_link_is_saved_using_real_model_fields(self, request):
        request.return_value.json.return_value = {'location': 'https://meet.google.com/abc-defg-hij'}
        refresh_consultation_meet_link(self.connection, self.consultation)
        self.consultation.refresh_from_db()
        self.assertEqual(self.consultation.google_meet_link, 'https://meet.google.com/abc-defg-hij')
        self.assertEqual(self.consultation.google_event_id, 'existing-event')

    @patch('apps.faculty.services.google_calendar.google_request')
    def test_missing_conference_patches_existing_event(self, request):
        link = 'https://meet.google.com/abc-defg-hij'
        request.side_effect = [Mock(json=lambda: {'id': 'existing-event'}), Mock(json=lambda: {'hangoutLink': link})]
        refresh_consultation_meet_link(self.connection, self.consultation)
        self.consultation.refresh_from_db()
        self.assertEqual(self.consultation.google_meet_link, link)
        self.assertEqual(self.consultation.google_event_id, 'existing-event')
        self.assertEqual([call.args[1] for call in request.call_args_list], ['GET', 'PATCH'])
        self.assertEqual(request.call_args.kwargs['params']['sendUpdates'], 'none')
        self.assertEqual(request.call_args.kwargs['json']['attendees'], [])

    @patch('apps.faculty.services.google_calendar.google_request')
    def test_generation_error_is_persisted(self, request):
        request.side_effect = GoogleCalendarError('Missing Meet permission')
        refresh_consultation_meet_link(self.connection, self.consultation)
        self.consultation.refresh_from_db()
        self.assertEqual(self.consultation.calendar_sync_error, 'Missing Meet permission')
        self.assertEqual(self.consultation.calendar_sync_status, 'failed')

    @patch('apps.faculty.services.google_calendar.google_request')
    def test_completed_consultation_never_regenerates_link(self, request):
        self.consultation.status = 'completed'
        refresh_consultation_meet_link(self.connection, self.consultation)
        request.assert_not_called()

    @patch('apps.faculty.services.google_calendar.google_request')
    def test_pending_conference_is_polled_without_creating_another(self, request):
        request.return_value.json.return_value = {
            'id': 'existing-event', 'conferenceData': {'createRequest': {'status': {'statusCode': 'pending'}}},
        }
        refresh_consultation_meet_link(self.connection, self.consultation)
        self.consultation.refresh_from_db()
        self.assertEqual(self.consultation.calendar_sync_status, 'pending')
        self.assertEqual(request.call_count, 1)
        request.return_value.json.return_value = {'hangoutLink': 'https://meet.google.com/abc-defg-hij'}
        refresh_consultation_meet_link(self.connection, self.consultation)
        self.consultation.refresh_from_db()
        self.assertTrue(self.consultation.google_meet_link)

    @patch('apps.faculty.services.google_calendar.google_request')
    def test_online_insert_requests_calendar_conference(self, request):
        self.consultation.google_event_id = None
        request.return_value.json.return_value = {'id': 'new-event'}
        create_consultation_event(self.connection, self.consultation)
        first = request.call_args.kwargs['json']['conferenceData']['createRequest']
        self.assertEqual(first['conferenceSolutionKey']['type'], 'hangoutsMeet')
        self.assertEqual(request.call_args.kwargs['params']['conferenceDataVersion'], 1)
        self.assertEqual(request.call_args.kwargs['params']['sendUpdates'], 'none')
        self.assertEqual(request.call_args.kwargs['json']['attendees'], [])
        create_consultation_event(self.connection, self.consultation)
        self.assertNotEqual(first['requestId'], request.call_args.kwargs['json']['conferenceData']['createRequest']['requestId'])

    @patch('apps.faculty.services.google_calendar.google_request')
    def test_face_to_face_has_no_conference(self, request):
        self.consultation.google_event_id = None
        self.consultation.mode = 'face_to_face'
        create_consultation_event(self.connection, self.consultation)
        self.assertNotIn('conferenceData', request.call_args.kwargs['json'])

    @patch('apps.faculty.services.google_calendar.google_request')
    def test_reschedule_does_not_replace_conference(self, request):
        update_consultation_event(self.connection, self.consultation)
        self.assertEqual(request.call_args.args[1], 'PATCH')
        self.assertEqual(request.call_args.kwargs['params']['sendUpdates'], 'none')
        self.assertEqual(request.call_args.kwargs['json']['attendees'], [])
        self.assertNotIn('conferenceData', request.call_args.kwargs['json'])

    @patch('apps.faculty.views.consultation_has_calendar_conflict', return_value=False)
    @patch('apps.faculty.services.google_calendar.google_request')
    def test_approval_persists_pending_event_then_both_users_receive_link(self, request, conflict):
        self.consultation.status = 'pending'
        self.consultation.google_event_id = None
        self.consultation.save()
        request.return_value.json.return_value = {
            'id': 'created-event', 'conferenceData': {'createRequest': {'status': {'statusCode': 'pending'}}},
        }
        self.client.force_login(self.connection.user)
        url = reverse('faculty:api_consultation', args=[self.consultation.pk])
        response = self.client.post(url, {'status': 'approved'}, content_type='application/json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['calendar_sync_status'], 'pending')
        self.consultation.refresh_from_db()
        self.assertEqual(self.consultation.google_event_id, 'created-event')
        link = 'https://meet.google.com/abc-defg-hij'
        request.return_value.json.return_value = {'id': 'created-event', 'hangoutLink': link}
        self.assertEqual(self.client.get(url).json()['google_meet_link'], link)
        with patch('apps.faculty.views.refresh_faculty_status'):
            self.assertContains(self.client.get(reverse('faculty:dashboard')), link)
        self.client.force_login(self.consultation.user)
        self.assertContains(self.client.get(reverse('students:consultation_requests')), link)

    @patch('apps.faculty.views.consultation_has_calendar_conflict', return_value=False)
    @patch('apps.faculty.services.google_calendar.google_request', side_effect=GoogleCalendarError('Invalid conference type value.'))
    def test_rejected_conference_leaves_request_pending(self, request, conflict):
        self.consultation.status = 'pending'
        self.consultation.google_event_id = None
        self.consultation.save()
        self.client.force_login(self.connection.user)
        response = self.client.post(reverse('faculty:api_consultation', args=[self.consultation.pk]), {'status': 'approved'}, content_type='application/json')
        self.assertEqual(response.status_code, 502)
        self.consultation.refresh_from_db()
        self.assertEqual(self.consultation.status, 'pending')
        self.assertIsNone(self.consultation.approved_at)

    @patch('apps.faculty.services.google_calendar.google_request')
    def test_completion_clears_link_and_deletes_event(self, request):
        self.consultation.google_meet_link = 'https://meet.google.com/abc-defg-hij'
        self.consultation.save()
        self.client.force_login(self.connection.user)
        response = self.client.post(reverse('faculty:api_consultation', args=[self.consultation.pk]), {'status': 'completed'}, content_type='application/json')
        self.assertEqual(response.status_code, 200)
        self.consultation.refresh_from_db()
        self.assertEqual(self.consultation.google_meet_link, '')
        self.assertIsNone(self.consultation.google_event_id)
        self.assertEqual(request.call_args.args[1], 'DELETE')
        self.assertEqual(request.call_args.kwargs['params']['sendUpdates'], 'none')
