from io import StringIO
from django.core.management import call_command, CommandError
from django.test import TestCase
from django.utils import timezone
from apps.core.models import College, User, DemoDataBatch
from apps.faculty.models import FacultyProfile, ConsultationRequest, StatusHistory, WalkInQueue


class DemoSeedTests(TestCase):
    def setUp(self):
        self.college, _ = College.objects.get_or_create(name='College of Computer Studies', defaults={'code': 'CCompS'})
        self.college.code = 'CCompS'
        self.college.save(update_fields=['code'])
        self.real = User.objects.create_user(username='real', college=self.college.code)

    def command(self, *args):
        out = StringIO()
        call_command('seed_demo_data', '--college', self.college.name, *args, stdout=out)
        return out.getvalue()

    def seed(self):
        preview = self.command('--dry-run')
        token = preview.split('Target confirmation: ')[1].splitlines()[0]
        self.command('--confirm-target', token)
        return token

    def test_dry_run_is_read_only_and_target_confirmation_required(self):
        preview = self.command('--dry-run')
        self.assertIn('code=CCompS', preview)
        self.assertEqual(User.objects.count(), 1)
        self.assertFalse(DemoDataBatch.objects.exists())
        with self.assertRaises(CommandError):
            self.command()

    def test_seed_and_exact_undo_preserve_real_user(self):
        token = self.seed()
        self.assertEqual(User.objects.count(), 25)
        self.assertEqual(FacultyProfile.objects.count(), 6)
        self.assertEqual(ConsultationRequest.objects.count(), 54)
        self.assertEqual(WalkInQueue.objects.count(), 10)
        self.assertTrue(all(f.college_id == self.college.code and f.manual_status_override and not f.sync_enabled for f in FacultyProfile.objects.all()))
        self.assertTrue(all(not u.has_usable_password() for u in User.objects.exclude(pk=self.real.pk)))
        for c in ConsultationRequest.objects.all():
            self.assertLess(c.requested_at, timezone.now())
            if c.approved_at:
                self.assertLess(c.requested_at, c.approved_at)
        self.assertIn('UNDO DRY RUN', self.command('--undo', '--dry-run'))
        self.command('--undo', '--confirm-target', token)
        self.assertEqual(list(User.objects.values_list('pk', flat=True)), [self.real.pk])
        self.assertFalse(StatusHistory.objects.exists())
        self.assertFalse(DemoDataBatch.objects.exists())

    def test_reseed_refuses_and_undo_rejects_real_dependency(self):
        token = self.seed()
        with self.assertRaises(CommandError):
            self.command('--confirm-target', token)
        f = FacultyProfile.objects.first()
        ConsultationRequest.objects.create(request_id='real-request', user=self.real, faculty=f, date=timezone.localdate())
        with self.assertRaisesMessage(CommandError, 'Outside dependency'):
            self.command('--undo', '--confirm-target', token)
        self.assertTrue(ConsultationRequest.objects.filter(pk='real-request').exists())
        self.assertEqual(User.objects.count(), 25)

    def test_modified_seeded_account_blocks_undo(self):
        token = self.seed()
        User.objects.filter(role='faculty').update(first_name='Changed')
        with self.assertRaisesMessage(CommandError, 'changed or removed'):
            self.command('--undo', '--confirm-target', token)
        self.assertEqual(User.objects.count(), 25)
