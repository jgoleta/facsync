from datetime import timedelta
from unittest.mock import patch, Mock

import requests
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.core.models import User, Notification
from apps.students.models import FacultyStatusSubscription
from apps.faculty.models import FacultyProfile, StatusHistory, StatusEmailDelivery, StatusSchedulerState
from apps.faculty.services.google_calendar import refresh_faculty_status
from apps.faculty.services.status_scheduler import acquire_lease, claim_deliveries, run_status_scheduler, submit_batch


@override_settings(AUTOMATIC_STATUS_EMAIL_QUEUE_ENABLED=True, STATUS_SCHEDULER_SECRET='test-secret',
                   BREVO_API_KEY='test-key', DEFAULT_FROM_EMAIL='facsync@example.com')
class StatusSchedulerTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='faculty', role='faculty', account_status='active', college='CCS')
        self.student = User.objects.create_user(username='student', role='student', account_status='active', email='student@example.com')
        self.faculty = FacultyProfile.objects.create(user=self.owner, faculty_id='f1', college_id='CCS', current_status='busy')
        FacultyStatusSubscription.objects.create(faculty=self.faculty, student=self.student)

    def enqueue(self):
        refresh_faculty_status(self.faculty)
        return StatusEmailDelivery.objects.get()

    @patch('apps.core.services.send_faculty_status_email')
    def test_page_change_is_durable_and_stale_object_does_not_duplicate(self, send):
        stale = FacultyProfile.objects.get(pk=self.faculty.pk)
        row = self.enqueue()
        refresh_faculty_status(stale)
        self.assertEqual(stale.current_status, 'not_set')
        self.assertEqual(row.state, 'pending')
        self.assertEqual(StatusHistory.objects.count(), 1)
        self.assertEqual(StatusEmailDelivery.objects.count(), 1)
        self.assertEqual(Notification.objects.filter(notification_type='faculty_status_update').count(), 1)
        send.assert_not_called()

    @patch('apps.core.services.send_faculty_status_email')
    def test_manual_update_sends_after_commit_without_queue(self, send):
        with self.captureOnCommitCallbacks(execute=True):
            refresh_faculty_status(self.faculty, immediate_email=True)
        send.assert_called_once()
        self.assertFalse(StatusEmailDelivery.objects.exists())

    @override_settings(AUTOMATIC_STATUS_EMAIL_QUEUE_ENABLED=False)
    @patch('apps.core.services.send_faculty_status_email')
    def test_disabled_queue_preserves_immediate_delivery(self, send):
        with self.captureOnCommitCallbacks(execute=True):
            refresh_faculty_status(self.faculty)
        send.assert_called_once()
        self.assertFalse(StatusEmailDelivery.objects.exists())

    @patch('apps.faculty.services.status_scheduler.submit_batch', return_value=('accepted', 'provider_accepted'))
    def test_scheduler_expires_manual_status_and_sends_without_page(self, submit):
        self.faculty.manual_status_override = True
        self.faculty.manual_status = 'busy'
        self.faculty.manual_status_expires_at = timezone.now() - timedelta(seconds=1)
        self.faculty.save()
        result = run_status_scheduler()
        self.faculty.refresh_from_db()
        self.assertEqual(self.faculty.current_status, 'not_set')
        self.assertTrue(self.faculty.manual_status_override)
        self.assertIsNone(self.faculty.manual_status_expires_at)
        self.assertEqual(result['email_claimed'], 1)
        self.assertEqual(StatusEmailDelivery.objects.get().state, 'accepted')
        run_status_scheduler()
        submit.assert_called_once()

    @patch('apps.faculty.services.status_scheduler.submit_batch', return_value=('accepted', 'provider_accepted'))
    def test_page_detected_transition_is_sent_by_scheduler(self, submit):
        self.enqueue()
        result = run_status_scheduler()
        self.assertEqual(result['changed'], 0)
        self.assertEqual(result['email_claimed'], 1)
        submit.assert_called_once()

    def test_lease_excludes_another_run_and_expired_lease_recovers(self):
        self.assertTrue(acquire_lease())
        self.assertIsNone(acquire_lease())
        self.assertEqual(run_status_scheduler(), {'skipped': 'already_running'})
        StatusSchedulerState.objects.update(lease_until=timezone.now() - timedelta(seconds=1))
        self.assertTrue(acquire_lease())

    def test_unsubscribed_recipient_cancelled_and_claim_not_reclaimed(self):
        row = self.enqueue()
        FacultyStatusSubscription.objects.all().delete()
        self.assertEqual(claim_deliveries(), [])
        row.refresh_from_db()
        self.assertEqual(row.state, 'cancelled')

    def test_abandoned_send_becomes_unknown_not_pending(self):
        row = self.enqueue()
        StatusEmailDelivery.objects.filter(pk=row.pk).update(state='sending', claimed_at=timezone.now() - timedelta(minutes=3))
        self.assertEqual(claim_deliveries(), [])
        row.refresh_from_db()
        self.assertEqual(row.state, 'unknown')

    @patch('apps.faculty.services.status_scheduler.submit_batch', return_value=('pending', 'rate_limited'))
    def test_safe_retry_is_bounded(self, submit):
        row = self.enqueue()
        for _ in range(3):
            StatusEmailDelivery.objects.filter(pk=row.pk).update(next_attempt_at=timezone.now())
            run_status_scheduler()
        row.refresh_from_db()
        self.assertEqual(row.state, 'failed')
        self.assertEqual(row.attempts, 3)

    @patch('apps.faculty.services.status_scheduler.requests.post')
    def test_private_batch_and_uncertain_timeout(self, post):
        rows = [self.enqueue()]
        response = Mock(status_code=201)
        response.json.return_value = {'messageIds': ['message-1']}
        post.return_value.__enter__.return_value = response
        self.assertEqual(submit_batch(rows)[0], 'accepted')
        payload = post.call_args.kwargs['json']
        self.assertNotIn('to', payload)
        self.assertEqual(payload['messageVersions'][0]['to'], [{'email': 'student@example.com'}])
        post.side_effect = requests.ReadTimeout()
        self.assertEqual(submit_batch(rows)[0], 'unknown')
        post.side_effect = requests.ConnectTimeout()
        self.assertEqual(submit_batch(rows)[0], 'pending')

    @patch('apps.faculty.scheduler_views.run_status_scheduler', return_value={'checked': 1})
    def test_endpoint_auth_method_and_no_cache(self, run):
        path = '/faculty/internal/automatic-status/'
        self.assertEqual(self.client.get(path).status_code, 405)
        self.assertEqual(self.client.post(path).status_code, 401)
        self.assertEqual(self.client.post(path, HTTP_AUTHORIZATION='Bearer wrong').status_code, 401)
        run.assert_not_called()
        response = self.client.post(path, HTTP_AUTHORIZATION='Bearer test-secret')
        self.assertEqual(response.status_code, 200)
        self.assertIn('no-store', response['Cache-Control'])
        run.assert_called_once()

    @override_settings(STATUS_SCHEDULER_SECRET='')
    def test_missing_secret_fails_closed(self):
        self.assertEqual(self.client.post('/faculty/internal/automatic-status/', HTTP_AUTHORIZATION='Bearer ').status_code, 401)

    def test_no_subscribers_produces_no_email(self):
        FacultyStatusSubscription.objects.all().delete()
        refresh_faculty_status(self.faculty)
        self.assertEqual(StatusHistory.objects.count(), 1)
        self.assertFalse(StatusEmailDelivery.objects.exists())

    def test_transition_rolls_back_if_queue_cannot_be_saved(self):
        with patch('apps.faculty.models.StatusEmailDelivery.objects.bulk_create', side_effect=RuntimeError('failure')):
            with self.assertRaises(RuntimeError):
                refresh_faculty_status(self.faculty)
        self.faculty.refresh_from_db()
        self.assertEqual(self.faculty.current_status, 'busy')
        self.assertFalse(StatusHistory.objects.exists())
        self.assertFalse(Notification.objects.exists())

    @patch('apps.faculty.services.status_scheduler.submit_batch', return_value=('unknown', 'transport_uncertain'))
    def test_unknown_delivery_is_not_automatically_retried(self, submit):
        self.enqueue()
        self.assertEqual(run_status_scheduler()['email_unknown'], 1)
        run_status_scheduler()
        submit.assert_called_once()

    @patch('apps.faculty.services.status_scheduler.submit_batch', return_value=('accepted', 'provider_accepted'))
    @patch('apps.faculty.services.status_scheduler.MAX_FACULTY', 1)
    def test_cursor_visits_later_faculty_and_keeps_manual_override(self, submit):
        other = User.objects.create_user(username='faculty2', role='faculty', account_status='active')
        second = FacultyProfile.objects.create(user=other, faculty_id='f2', current_status='busy')
        first = run_status_scheduler()
        self.assertEqual(first['checked'], 1)
        second.refresh_from_db()
        self.assertEqual(second.current_status, 'busy')
        run_status_scheduler()
        second.refresh_from_db()
        self.assertEqual(second.current_status, 'not_set')
        self.faculty.manual_status_override = True
        self.faculty.manual_status = 'available'
        self.faculty.current_status = 'available'
        self.faculty.save()
        run_status_scheduler()
        self.faculty.refresh_from_db()
        self.assertEqual(self.faculty.current_status, 'available')

    @override_settings(BREVO_API_KEY='')
    @patch('apps.faculty.scheduler_views.run_status_scheduler')
    def test_missing_email_credentials_does_not_run(self, run):
        response = self.client.post('/faculty/internal/automatic-status/', HTTP_AUTHORIZATION='Bearer test-secret')
        self.assertEqual(response.status_code, 503)
        run.assert_not_called()

    @patch('apps.core.services.send_faculty_status_email')
    def test_real_manual_endpoint_remains_immediate(self, send):
        self.client.force_login(self.owner)
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post('/faculty/api/status/', data={'status': 'available'}, content_type='application/json')
        self.assertEqual(response.status_code, 200)
        send.assert_called_once()
        self.assertFalse(StatusEmailDelivery.objects.exists())
