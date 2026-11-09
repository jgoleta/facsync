from copy import deepcopy
from django.test import SimpleTestCase
from scripts.recover_consultation_history import plan, verify_backup


class ConsultationRecoveryPlanTests(SimpleTestCase):
    def setUp(self):
        school = {'id': 1, 'code': 'SCHOOL', 'name': 'School'}
        student = {'id': 1, 'username': 'student', 'email': 'student@school.org', 'role': 'student',
                   'school_id': 1, 'department_id': None, 'password': 'never-restore-this'}
        faculty = dict(student, id=2, username='faculty', email='faculty@school.org', role='faculty')
        request = {'request_id': 'missing', 'user_id': 1, 'faculty_id': 'old', 'department_id': None,
                   'status': 'completed', 'date': '2026-10-01', 'agenda': 'academic_advising'}
        self.source = {'schools': [school], 'departments': [], 'users': [student, faculty],
                       'faculty': [{'faculty_id': 'old', 'user_id': 2, 'college_id': 'OFFICE'}], 'requests': [request]}
        replacement = dict(faculty, id=30)
        self.target = {'schools': [school.copy()], 'departments': [], 'users': [replacement],
                       'faculty': [{'faculty_id': 'replacement', 'user_id': 30, 'college_id': 'OFFICE'}], 'requests': []}

    def test_missing_student_is_archived_and_faculty_is_mapped_without_mutating_sources(self):
        before = deepcopy((self.source, self.target))
        result = plan(self.source, self.target)
        archive = result['archived_students'][0]
        self.assertEqual(archive['password'], '!')
        self.assertFalse(archive['is_active'])
        self.assertFalse(archive['is_staff'])
        self.assertFalse(archive['is_superuser'])
        self.assertEqual(archive['account_status'], 'deactivated')
        self.assertEqual(result['requests'][0]['faculty_id'], 'replacement')
        self.assertIsNone(result['requests'][0]['department_id'])
        self.assertEqual((self.source, self.target), before)

    def test_existing_requests_are_never_replaced(self):
        self.target['requests'] = [dict(self.source['requests'][0], status='cancelled')]
        result = plan(self.source, self.target)
        self.assertEqual(result['requests'], [])
        self.assertEqual(result['archived_students'], [])
        self.assertEqual(self.target['requests'][0]['status'], 'cancelled')

    def test_cross_school_faculty_is_rejected(self):
        self.target['users'][0]['school_id'] = 2
        with self.assertRaises(ValueError):
            plan(self.source, self.target)

    def test_duplicate_student_identity_requires_explicit_review(self):
        self.target['users'].append(dict(self.source['users'][0], id=31))
        with self.assertRaisesMessage(ValueError, 'replacement'):
            plan(self.source, self.target)

    def test_changed_faculty_unit_is_rejected(self):
        self.target['faculty'][0]['college_id'] = 'DIFFERENT'
        with self.assertRaisesMessage(ValueError, 'unit'):
            plan(self.source, self.target)

    def test_backup_must_match_rehearsal_requests(self):
        rows = deepcopy(self.source['requests'])
        rows[0] = {key: str(value) if value is not None else None for key, value in rows[0].items()}
        verify_backup(self.source, rows)
        rows[0]['status'] = 'approved'
        with self.assertRaisesMessage(ValueError, 'differs'):
            verify_backup(self.source, rows)
