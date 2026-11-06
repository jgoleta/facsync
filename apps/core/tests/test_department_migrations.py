from datetime import timedelta
from importlib import import_module

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from django.utils import timezone


class DepartmentMigrationTests(TransactionTestCase):
    before = [('core', '0025_alter_user_role_officeadmininvite_office'),
              ('faculty', '0033_consultationrequest_google_meet_link'),
              ('depthead', '0002_collegeaiinsight_school_and_more')]
    after = [('core', '0027_attach_adnu_departments'), ('faculty', '0034_department_foundation'),
             ('depthead', '0002_collegeaiinsight_school_and_more')]

    def migrate(self, targets):
        executor = MigrationExecutor(connection)
        executor.migrate(targets)
        return executor.loader.project_state(targets).apps

    def setUp(self):
        super().setUp()
        # Restore leaves even if an older repository migration test left an old schema.
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
        self.old = self.migrate(self.before)
        self.cleanup = []
        self.school, _ = self.old.get_model('core', 'School').objects.get_or_create(
            code='ADNU', defaults={'name': 'Ateneo de Naga University'})
        self.colleges = {}
        for code in ('CBA', 'CCS', 'CED', 'CHSS', 'CON', 'CSEA', 'COL'):
            college, _ = self.old.get_model('core', 'College').objects.get_or_create(
                school_id=self.school.pk, code=code, defaults={'name': f'College {code}'})
            college.schedule_template = {'title': 'SUBJECT'}
            college.save()
            self.colleges[code] = college
        users = self.old.get_model('core', 'User').objects
        self.student = users.create(username='migration-student', role='student', school_id=self.school.pk,
                                    college='cba', year_level='2', profile_completed=True)
        self.teacher = users.create(username='migration-teacher', role='faculty', school_id=self.school.pk, college='ccs')
        self.head = users.create(username='migration-head', role='depthead', school_id=self.school.pk, college='CCS', title='dean')
        self.profile = self.old.get_model('faculty', 'FacultyProfile').objects.create(
            user_id=self.teacher.pk, faculty_id='migration-teacher', college_id='CCS', current_status='busy')
        self.consultation = self.old.get_model('faculty', 'ConsultationRequest').objects.create(
            user_id=self.student.pk, faculty_id=self.profile.pk, request_id='migration-consultation',
            date='2026-11-10', status='approved', google_event_id='unchanged-google-event',
            google_calendar_id='primary', google_meet_link='https://meet.google.com/example')
        self.old.get_model('faculty', 'ScheduleEvent').objects.create(
            faculty_id=self.profile.pk, title='Existing event', date='2026-11-10', google_event_id='schedule-google-id')
        self.invite = self.old.get_model('core', 'DeptHeadInvite').objects.create(
            school_id=self.school.pk, email='invited-head@example.invalid', college='CCS', title='chairperson')
        self.old.get_model('core', 'FacultyInvite').objects.create(
            school_id=self.school.pk, email='invited-faculty@example.invalid', college='CCS')
        self.old.get_model('core', 'CollegeAnnouncement').objects.create(
            school_id=self.school.pk, college='CCS', posted_by_id=self.head.pk, message='Keep this notice',
            expiry=timezone.now() + timedelta(days=2))
        self.old.get_model('core', 'OfficeClosure').objects.create(
            school_id=self.school.pk, college='CCS', is_closed=True, reason='Keep this reason')
        self.old.get_model('depthead', 'CollegeAIInsight').objects.create(
            school_id=self.school.pk, college_code='CCS', analytics_hash='a' * 64, insights={'summary': 'Keep this cache'},
            model_name='test', generated_at=timezone.now(), refresh_after=timezone.now() + timedelta(days=7))

    def tearDown(self):
        try:
            for cleanup in reversed(self.cleanup):
                cleanup()
            executor = MigrationExecutor(connection)
            executor.migrate(executor.loader.graph.leaf_nodes())
        finally:
            super().tearDown()

    def test_maps_all_approved_colleges_and_preserves_legacy_links(self):
        new = self.migrate(self.after)
        departments = new.get_model('core', 'Department').objects
        self.assertEqual(dict(departments.values_list('college__code', 'name')), {
            'CBA': 'Department of Accountancy', 'CCS': 'Department of Computer Science',
            'CED': 'Department of Elementary Education', 'CHSS': 'Department of Media Studies',
            'CON': 'Department of Nursing', 'CSEA': 'Department of Civil Engineering', 'COL': 'Department of Law',
        })
        dcs = departments.get(code='DCS')
        self.assertEqual(dcs.schedule_template, {'title': 'SUBJECT'})
        users = new.get_model('core', 'User').objects
        teacher = users.get(pk=self.teacher.pk)
        self.assertEqual(teacher.department_id, dcs.pk)
        self.assertEqual(teacher.college, 'ccs')
        self.assertEqual(users.get(pk=self.student.pk).department.code, 'DA')
        self.assertEqual(users.get(pk=self.student.pk).year_level, '2')
        head = users.get(pk=self.head.pk)
        self.assertIsNone(head.department_id)
        self.assertEqual(head.title, 'dean')
        self.assertEqual(list(head.managed_departments.values_list('pk', flat=True)), [dcs.pk])
        self.assertEqual(new.get_model('core', 'DeptHeadInvite').objects.get(pk=self.invite.pk).departments.get().pk, dcs.pk)
        self.assertEqual(new.get_model('core', 'FacultyInvite').objects.get().department_id, dcs.pk)
        self.assertEqual(new.get_model('core', 'CollegeAnnouncement').objects.get().department_id, dcs.pk)
        self.assertEqual(new.get_model('core', 'OfficeClosure').objects.get().department_id, dcs.pk)
        item = new.get_model('faculty', 'ConsultationRequest').objects.get(pk=self.consultation.pk)
        self.assertEqual(item.department_id, dcs.pk)  # Faculty scope, not the student's CBA.
        self.assertEqual(item.faculty_id, self.profile.pk)
        self.assertEqual(item.user_id, self.student.pk)
        self.assertEqual(item.google_event_id, 'unchanged-google-event')
        self.assertEqual(item.google_meet_link, 'https://meet.google.com/example')
        self.assertEqual(item.status, 'approved')
        self.assertEqual(new.get_model('faculty', 'ScheduleEvent').objects.get().google_event_id, 'schedule-google-id')
        cache = new.get_model('depthead', 'CollegeAIInsight').objects.get()
        self.assertEqual(cache.analytics_hash, 'a' * 64)
        self.assertEqual(cache.insights, {'summary': 'Keep this cache'})

    def test_office_records_are_not_converted_to_academic_departments(self):
        self.old.get_model('core', 'Office').objects.create(school_id=self.school.pk, code='GUIDANCE', name='Guidance')
        user = self.old.get_model('core', 'User').objects.create(
            username='office-owner', role='officeadmin', school_id=self.school.pk, college='GUIDANCE')
        self.old.get_model('faculty', 'FacultyProfile').objects.create(
            user_id=user.pk, faculty_id='office-owner', college_id='GUIDANCE')
        self.old.get_model('core', 'OfficeClosure').objects.create(school_id=self.school.pk, college='GUIDANCE')
        new = self.migrate(self.after)
        self.assertIsNone(new.get_model('core', 'User').objects.get(pk=user.pk).department_id)
        self.assertIsNone(new.get_model('core', 'OfficeClosure').objects.get(college='GUIDANCE').department_id)
        self.assertEqual(new.get_model('core', 'Office').objects.get().code, 'GUIDANCE')

    def test_unknown_reference_refuses_before_any_backfill_write(self):
        user = self.old.get_model('core', 'User').objects.create(
            username='unknown-unit', role='faculty', school_id=self.school.pk, college='CCS2')
        self.cleanup.append(lambda: user.delete())
        with self.assertRaisesRegex(RuntimeError, 'unknown unit'):
            self.migrate(self.after)
        state = MigrationExecutor(connection).loader.project_state([('core', '0026_department_foundation')]).apps
        self.assertFalse(state.get_model('core', 'Department').objects.exists())

    def test_disagreeing_profile_refuses_before_any_backfill_write(self):
        self.profile.college_id = 'CBA'
        self.profile.save()
        def restore():
            self.profile.college_id = 'CCS'
            self.profile.save()
        self.cleanup.append(restore)
        with self.assertRaisesRegex(RuntimeError, 'disagreement'):
            self.migrate(self.after)

    def test_other_school_academic_data_requires_an_explicit_mapping(self):
        school = self.old.get_model('core', 'School').objects.create(code='OTHER', name='Other school')
        self.old.get_model('core', 'College').objects.create(school_id=school.pk, code='CCS', name='Other CCS')
        user = self.old.get_model('core', 'User').objects.create(
            username='other-school-student', role='student', school_id=school.pk, college='CCS')
        self.cleanup.append(lambda: user.delete())
        with self.assertRaisesRegex(RuntimeError, 'explicit school/college mapping'):
            self.migrate(self.after)

    def test_pristine_mapping_can_be_reversed_without_losing_legacy_records(self):
        self.migrate(self.after)
        old = self.migrate(self.before)
        self.assertEqual(old.get_model('core', 'User').objects.get(pk=self.teacher.pk).college, 'ccs')
        self.assertEqual(old.get_model('faculty', 'ConsultationRequest').objects.get(pk=self.consultation.pk).google_event_id,
                         'unchanged-google-event')
        self.assertEqual(old.get_model('core', 'DeptHeadInvite').objects.get(pk=self.invite.pk).college, 'CCS')

    def test_demo_manifest_is_refreshed_only_for_unchanged_owned_records(self):
        migration = import_module('apps.core.migrations.0027_attach_adnu_departments')
        teacher_hash = migration.fingerprint(self.teacher)
        student_hash = migration.fingerprint(self.student)
        batch = self.old.get_model('core', 'DemoDataBatch').objects.create(
            key='department-migration-test', college_id=self.colleges['CCS'].pk,
            manifest={'core.User': {str(self.teacher.pk): teacher_hash, str(self.student.pk): student_hash}})
        self.student.first_name = 'Edited since seeding'
        self.student.save()
        new = self.migrate(self.after)
        manifest = new.get_model('core', 'DemoDataBatch').objects.get(pk=batch.pk).manifest['core.User']
        teacher = new.get_model('core', 'User').objects.get(pk=self.teacher.pk)
        self.assertEqual(manifest[str(self.teacher.pk)], migration.fingerprint(teacher))
        self.assertEqual(manifest[str(self.student.pk)], student_hash)
        old = self.migrate(self.before)
        self.assertEqual(old.get_model('core', 'DemoDataBatch').objects.get(pk=batch.pk).manifest['core.User'][str(self.teacher.pk)],
                         teacher_hash)

    def test_rollback_refuses_multiple_assignments_instead_of_discarding_them(self):
        new = self.migrate(self.after)
        extra = new.get_model('core', 'DepartmentHeadAssignment').objects.create(
            user_id=self.head.pk, department_id=new.get_model('core', 'Department').objects.get(code='DA').pk)
        self.cleanup.append(lambda: extra.delete())
        with self.assertRaisesRegex(RuntimeError, 'head assignments changed'):
            self.migrate(self.before)
        self.assertEqual(new.get_model('core', 'DepartmentHeadAssignment').objects.filter(user_id=self.head.pk).count(), 2)

    def test_rollback_refuses_new_membership_without_legacy_college(self):
        new = self.migrate(self.after)
        user = new.get_model('core', 'User').objects.create(
            username='new-department-only-student', role='student', school_id=self.school.pk,
            department_id=new.get_model('core', 'Department').objects.get(code='DCS').pk,
            college=None, profile_completed=False)
        self.cleanup.append(lambda: user.delete())
        with self.assertRaisesRegex(RuntimeError, 'no legacy college representation'):
            self.migrate(self.before)
        self.assertIsNotNone(new.get_model('core', 'User').objects.get(pk=user.pk).department_id)
