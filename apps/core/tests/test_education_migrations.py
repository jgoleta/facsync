from importlib import import_module

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class EducationMigrationTests(TransactionTestCase):
    before = [('core', '0029_department_closure_scope')]
    after = [('core', '0031_classify_existing_students')]

    def migrate(self, targets):
        executor = MigrationExecutor(connection)
        executor.migrate(targets)
        return executor.loader.project_state(targets).apps

    def setUp(self):
        super().setUp()
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
        old = self.migrate(self.before)
        self.old = old
        self.school, _ = old.get_model('core', 'School')._base_manager.get_or_create(code='ADNU', defaults={'name': 'ADNU'})
        self.college, _ = old.get_model('core', 'College')._base_manager.get_or_create(school_id=self.school.pk, code='CCS', defaults={'name': 'College of Computer Studies'})
        self.department, _ = old.get_model('core', 'Department')._base_manager.get_or_create(school_id=self.school.pk,
            code='DCS', defaults={'name': 'Department of Computer Science', 'college_id': self.college.pk})
        self.student = old.get_model('core', 'User')._base_manager.create(username='education-migration-student',
            school_id=self.school.pk, role='student', college='CCS', department_id=self.department.pk,
            year_level='2', student_id='OLD-ID', profile_completed=True)

    def tearDown(self):
        # Each refusal test restores representable source data before restoring leaves.
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
        super().tearDown()

    def test_backfill_preserves_ids_roles_membership_and_year(self):
        new = self.migrate(self.after)
        item = new.get_model('core', 'User')._base_manager.get(pk=self.student.pk)
        self.assertEqual((item.role, item.department_id, item.student_id, item.year_level, item.profile_completed),
            ('student', self.department.pk, 'OLD-ID', '2', True))
        self.assertEqual(item.educational_level, 'college')
        self.assertEqual(new.get_model('core', 'School')._base_manager.get(pk=self.school.pk).educational_levels, ['college'])
        restored = self.migrate(self.before)
        self.assertEqual(restored.get_model('core', 'User')._base_manager.get(pk=item.pk).student_id, 'OLD-ID')

    def test_invalid_completed_profile_refuses_before_classification(self):
        self.student.department_id = None
        self.student.save()
        with self.assertRaisesRegex(RuntimeError, 'Completed student profiles'):
            self.migrate(self.after)
        schema = MigrationExecutor(connection).loader.project_state([('core', '0030_educational_levels')]).apps
        user = schema.get_model('core', 'User')._base_manager.get(pk=self.student.pk)
        self.assertEqual(user.educational_level, '')
        user.department_id = self.department.pk
        user.save()

    def test_reverse_refuses_basic_education_then_allows_restored_state(self):
        new = self.migrate(self.after)
        school = new.get_model('core', 'School')._base_manager.get(pk=self.school.pk)
        school.educational_levels = ['jhs', 'college']
        school.save()
        with self.assertRaisesRegex(RuntimeError, 'school changes'):
            self.migrate(self.before)
        school.educational_levels = ['college']
        school.save()
        student = new.get_model('core', 'User')._base_manager.get(pk=self.student.pk)
        student.educational_level = 'shs'
        student.year_level = '12'
        student.save()
        with self.assertRaisesRegex(RuntimeError, 'previous schema'):
            self.migrate(self.before)
        student.educational_level = 'college'
        student.year_level = '2'
        student.save()

    def test_unchanged_demo_fingerprints_follow_schema_changes(self):
        migration = import_module('apps.core.migrations.0031_classify_existing_students')
        original = migration.fingerprint(self.student)
        batch = self.old.get_model('core', 'DemoDataBatch')._base_manager.create(
            key='education-fingerprints', college_id=self.college.pk,
            manifest={'core.User': {str(self.student.pk): original}})
        new = self.migrate(self.after)
        current = new.get_model('core', 'User')._base_manager.get(pk=self.student.pk)
        saved = new.get_model('core', 'DemoDataBatch')._base_manager.get(pk=batch.pk)
        self.assertEqual(saved.manifest['core.User'][str(current.pk)], migration.fingerprint(current))
        restored = self.migrate(self.before)
        old_batch = restored.get_model('core', 'DemoDataBatch')._base_manager.get(pk=batch.pk)
        self.assertEqual(old_batch.manifest['core.User'][str(current.pk)], original)
