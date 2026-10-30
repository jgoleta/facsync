from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from apps.core.tests.school_case import SchoolTestCase as TestCase

from apps.core.management.commands.seed_staging_data import KEY, MODELS, PREFIX, Command
from apps.core.models import College, DemoDataBatch, FacultyInvite, User
from apps.faculty.models import ConsultationRequest, GoogleCalendarConnection


class StagingSeedTests(TestCase):
    def run_seed(self, *args):
        with patch.object(Command, 'verify_target'):
            call_command('seed_staging_data', *args, stdout=StringIO())

    def test_default_preview_writes_nothing(self):
        counts = {model: model.objects.count() for model in MODELS}
        self.run_seed()
        self.assertEqual(counts, {model: model.objects.count() for model in MODELS})
        self.assertFalse(DemoDataBatch.objects.filter(key=KEY).exists())

    def test_non_staging_target_is_rejected(self):
        with self.assertRaisesMessage(CommandError, 'requires config.settings.staging'):
            call_command('seed_staging_data', '--apply', stdout=StringIO())
        self.assertFalse(User.objects.exists())

    @patch('requests.sessions.Session.request', side_effect=AssertionError('External HTTP forbidden'))
    @patch('django.core.mail.send_mail', side_effect=AssertionError('Email forbidden'))
    def test_representative_data_and_safe_undo(self, mail, http):
        outside = User.objects.create_user(username='outside-sample', role='student')
        original_colleges = list(College.objects.order_by('pk').values())
        self.run_seed('--apply')
        users = User.objects.filter(username__startswith=PREFIX)
        self.assertEqual(users.count(), 16)
        self.assertEqual(set(users.values_list('role', flat=True)), {'superadmin','depthead','faculty','student'})
        self.assertEqual(users.filter(role='superadmin', account_status='active', college__isnull=True).count(), 2)
        self.assertTrue(all(not user.has_usable_password() for user in users))
        self.assertEqual(set(ConsultationRequest.objects.values_list('status', flat=True)), set(dict(ConsultationRequest.STATUS_CHOICES)))
        self.assertEqual(DemoDataBatch.objects.get(key=KEY).manifest.keys(), {model._meta.label for model in MODELS})
        self.assertEqual(GoogleCalendarConnection.objects.count(), 0)
        self.assertTrue(FacultyInvite.objects.filter(used=False).exists())
        self.assertTrue(FacultyInvite.objects.filter(used=True).exists())
        self.run_seed('--undo')
        self.assertTrue(users.exists())
        self.run_seed('--undo', '--apply')
        self.assertFalse(User.objects.filter(username__startswith=PREFIX).exists())
        self.assertTrue(User.objects.filter(pk=outside.pk).exists())
        self.assertFalse(DemoDataBatch.objects.filter(key=KEY).exists())
        self.assertEqual(original_colleges, list(College.objects.order_by('pk').values()))
        mail.assert_not_called()
        http.assert_not_called()

    def test_repeat_create_refuses_without_changes(self):
        self.run_seed('--apply')
        count = User.objects.count()
        with self.assertRaisesMessage(CommandError, 'already exists'):
            self.run_seed('--apply')
        self.assertEqual(User.objects.count(), count)

    def test_modified_sample_blocks_undo(self):
        self.run_seed('--apply')
        User.objects.filter(username=PREFIX + 'student-1').update(first_name='Edited')
        with self.assertRaisesMessage(CommandError, 'changed or removed'):
            self.run_seed('--undo', '--apply')
        self.assertEqual(User.objects.filter(username__startswith=PREFIX).count(), 16)

    def test_outside_dependency_blocks_undo(self):
        self.run_seed('--apply')
        FacultyInvite.objects.create(
            email='outside@example.invalid', college='CCS',
            invited_by=User.objects.get(username=PREFIX + 'head-1'),
        )
        with self.assertRaisesMessage(CommandError, 'Outside dependency'):
            self.run_seed('--undo', '--apply')
        self.assertTrue(DemoDataBatch.objects.filter(key=KEY).exists())
