import hashlib
import json

from django.core.serializers.json import DjangoJSONEncoder
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from django.utils import timezone


OLD = [('core', '0019_demodatabatch'), ('depthead', '0001_initial'), ('faculty', '0029_statusemaildelivery_html_body')]
NEW = [('core', '0023_alter_user_role_superadmininvite'), ('depthead', '0002_collegeaiinsight_school_and_more')]


def snapshot(obj):
    fields = {field.attname: getattr(obj, field.attname) for field in obj._meta.concrete_fields}
    return hashlib.sha256(json.dumps(fields, cls=DjangoJSONEncoder, sort_keys=True).encode()).hexdigest()


class SchoolMigrationTests(TransactionTestCase):
    def migrate(self, targets):
        executor = MigrationExecutor(connection)
        executor.migrate(targets)
        return executor.loader.project_state(targets).apps

    def setUp(self):
        super().setUp()
        # Other TransactionTestCases flush seeded data without rerunning data
        # migrations. Reconstruct only this test's empty bootstrap state.
        if 'core_school' in connection.introspection.table_names():
            executor = MigrationExecutor(connection)
            state = executor.loader.project_state(executor.loader.graph.leaf_nodes()).apps
            School = state.get_model('core', 'School')
            if not School.objects.exists():
                School.objects.create(code='ADNU', name='Ateneo de Naga University')
        self.old = self.migrate(OLD)
        from apps.core.colleges import COLLEGE_CHOICES
        for code, name in COLLEGE_CHOICES:
            self.old.get_model('core', 'College').objects.get_or_create(code=code.upper(), defaults={'name': name})

    def tearDown(self):
        # Restore the current schema even when an assertion or guarded reverse fails.
        executor = MigrationExecutor(connection)
        # A guarded rollback can already have removed later migrations. Use the
        # applied state so deletion does not traverse tables no longer present.
        state = executor.loader.project_state(list(executor.loader.applied_migrations)).apps
        if 'core_school' in connection.introspection.table_names():
            state.get_model('core', 'SchoolDomain').objects.all().delete()
            state.get_model('core', 'SchoolChangeLog').objects.all().delete()
            state.get_model('core', 'School').objects.exclude(code='ADNU').delete()
        self.migrate(NEW)
        super().tearDown()

    def legacy_rows(self):
        User = self.old.get_model('core', 'User')
        users = [User.objects.create(username='legacy-' + role, role=role, college='ccs' if role in {'student','faculty','depthead'} else None)
                 for role in ('superadmin','depthead','faculty','student')]
        Faculty = self.old.get_model('faculty', 'FacultyProfile')
        faculty = Faculty.objects.create(faculty_id='legacy-faculty', user_id=users[2].pk, college_id='CCS', sync_enabled=False)
        consultation = self.old.get_model('faculty','ConsultationRequest').objects.create(request_id='legacy-consultation', user_id=users[3].pk, faculty_id=faculty.pk, date=timezone.now().date())
        for label in ('FacultyInvite','DeptHeadInvite'):
            self.old.get_model('core',label).objects.create(email=label.lower()+'@example.invalid',college='CCS',invited_by_id=users[0].pk)
        self.old.get_model('core','OfficeClosure').objects.create(college='CCS',is_closed=True)
        self.old.get_model('core','CollegeAnnouncement').objects.create(college='ccs',message='Preserve this',posted_by_id=users[1].pk,expiry=timezone.now())
        self.old.get_model('depthead','CollegeAIInsight').objects.create(college_code='CCS',analytics_hash='0'*64,insights={},model_name='fixture',generated_at=timezone.now(),refresh_after=timezone.now())
        self.old.get_model('core','DemoDataBatch').objects.create(key='migration-fixture',college_id=self.old.get_model('core','College').objects.get(code='CCS').pk,manifest={'core.User':{str(users[0].pk):snapshot(users[0])}})
        return users, faculty, consultation

    def test_forward_backfill_and_reverse_preserve_records_roles_and_manifest(self):
        users, faculty, consultation = self.legacy_rows()
        original_hash = snapshot(users[0])
        apps = self.migrate(NEW)
        adnu = apps.get_model('core','School').objects.get(code='ADNU')
        self.assertFalse(apps.get_model('core','SchoolDomain').objects.exists())
        self.assertFalse(apps.get_model('core','SchoolChangeLog').objects.exists())
        for app,label in [('core','College'),('core','User'),('core','FacultyInvite'),('core','DeptHeadInvite'),('core','OfficeClosure'),('core','CollegeAnnouncement'),('depthead','CollegeAIInsight')]:
            self.assertFalse(apps.get_model(app,label).objects.exclude(school_id=adnu.pk).exists())
        admin = apps.get_model('core','User').objects.get(pk=users[0].pk)
        self.assertEqual(admin.role,'superadmin')
        self.assertEqual(apps.get_model('faculty','FacultyProfile').objects.get(pk=faculty.pk).college_id,'CCS')
        self.assertEqual(apps.get_model('faculty','ConsultationRequest').objects.get(pk=consultation.pk).user_id,users[3].pk)
        batch = apps.get_model('core','DemoDataBatch').objects.get(key='migration-fixture')
        self.assertEqual(batch.manifest['core.User'][str(admin.pk)],snapshot(admin))
        restored = self.migrate(OLD)
        restored_admin = restored.get_model('core','User').objects.get(pk=users[0].pk)
        self.assertEqual(snapshot(restored_admin),original_hash)
        self.assertEqual(restored.get_model('core','DemoDataBatch').objects.get(key='migration-fixture').manifest['core.User'][str(admin.pk)],original_hash)

    def test_unresolved_college_refuses_without_partial_backfill(self):
        self.old.get_model('core','User').objects.create(username='orphan',college='UNKNOWN')
        with self.assertRaisesRegex(RuntimeError,'unresolved college'):
            self.migrate(NEW)
        self.old.get_model('core','User').objects.filter(username='orphan').update(college=None)

    def test_faculty_college_disagreement_is_not_silently_repaired(self):
        users, faculty, _ = self.legacy_rows()
        self.old.get_model('faculty','FacultyProfile').objects.filter(pk=faculty.pk).update(college_id='CON')
        with self.assertRaisesRegex(RuntimeError,'disagreement'):
            self.migrate(NEW)
        self.old.get_model('faculty','FacultyProfile').objects.filter(pk=faculty.pk).update(college_id='CCS')

    def test_rollback_refuses_after_domain_assignment(self):
        apps = self.migrate(NEW)
        adnu = apps.get_model('core','School').objects.get(code='ADNU')
        apps.get_model('core','SchoolDomain').objects.create(school_id=adnu.pk,domain='adnu.edu.ph')
        with self.assertRaisesRegex(RuntimeError,'rollback refused'):
            self.migrate(OLD)

    def test_rollback_refuses_when_a_second_school_exists(self):
        apps = self.migrate(NEW)
        apps.get_model('core','School').objects.create(code='OTHER',name='Other institution')
        with self.assertRaisesRegex(RuntimeError,'rollback refused'):
            self.migrate(OLD)
