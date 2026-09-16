from unittest.mock import patch
from django.test import TestCase
from django.urls import reverse
from apps.core.models import User, OfficeClosure, CollegeAnnouncement, Notification


class SettingsNotificationTests(TestCase):
    def setUp(self):
        self.head = User.objects.create_user(username='head', role='depthead', college='ccs')
        self.faculty = User.objects.create_user(username='faculty', role='faculty', college='ccs')
        self.closure = OfficeClosure.objects.create(college='ccs')
        self.client.force_login(self.head)
        self.url = reverse('depthead:college_settings')

    def test_only_open_to_closed_emails(self):
        with patch('apps.depthead.views.send_closure_email_to_faculty') as send:
            for state, expected in [(True, 1), (True, 1), (False, 1), (False, 1), (True, 2)]:
                response = self.client.post(self.url, {'is_closed': 'on' if state else '', 'reason': 'Updated'})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()['is_closed'], state)
                self.assertEqual(send.call_count, expected)

    def test_closure_email_failure_keeps_saved_action_successful(self):
        with patch('apps.depthead.views.send_closure_email_to_faculty', side_effect=RuntimeError('failed')):
            with self.assertLogs('apps.depthead.views', level='ERROR'):
                response = self.client.post(self.url, {'is_closed': 'on'})
        self.assertTrue(response.json()['success'])
        self.closure.refresh_from_db()
        self.assertTrue(self.closure.is_closed)

    def test_announcement_email_failure_preserves_announcement_and_notifications(self):
        with patch('apps.depthead.views.send_announcement_email_to_faculty', side_effect=RuntimeError('failed')):
            with self.assertLogs('apps.depthead.views', level='ERROR'):
                response = self.client.post(reverse('depthead:create_announcement'), {'message': 'Notice', 'audience': 'both'})
        self.assertTrue(response.json()['success'])
        self.assertTrue(CollegeAnnouncement.objects.filter(message='Notice').exists())
        self.assertTrue(Notification.objects.filter(recipient=self.faculty, message='Notice').exists())

    def test_actual_database_state_wins_over_stale_form_instance(self):
        from apps.depthead.forms import OfficeClosureForm
        original = OfficeClosureForm.is_valid
        def validate_and_change_database(form):
            valid = original(form)
            OfficeClosure.objects.filter(pk=self.closure.pk).update(is_closed=True)
            return valid
        with patch.object(OfficeClosureForm, 'is_valid', validate_and_change_database):
            with patch('apps.depthead.views.send_closure_email_to_faculty') as send:
                response = self.client.post(self.url, {'is_closed': 'on'})
        self.assertTrue(response.json()['success'])
        send.assert_not_called()

    def test_status_endpoint_permissions_scope_and_read_only_behavior(self):
        url = reverse('depthead:closure_status')
        OfficeClosure.objects.create(college='con', is_closed=True)
        self.assertEqual(self.client.get(url + '?college=con').json(), {'is_closed': False})
        self.assertEqual(self.client.post(url).status_code, 405)
        self.assertIn('no-store', self.client.get(url)['Cache-Control'])
        self.closure.delete()
        self.assertEqual(self.client.get(url).json(), {'is_closed': False})
        self.assertFalse(OfficeClosure.objects.filter(college='ccs').exists())
        self.client.force_login(self.faculty)
        self.assertEqual(self.client.get(url).status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.get(url).status_code, 302)

    def test_invalid_closure_does_not_email(self):
        with patch('apps.depthead.views.send_closure_email_to_faculty') as send:
            response = self.client.post(self.url, {'is_closed': 'on', 'closure_start': 'invalid'})
        self.assertFalse(response.json()['success'])
        send.assert_not_called()

    def test_settings_contains_live_badge_and_shared_confirmation(self):
        response = self.client.get(self.url)
        self.assertContains(response, 'id="closure-status"')
        self.assertContains(response, 'id="settings-confirm"')
        self.assertContains(response, reverse('depthead:closure_status'))
