from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.test import TestCase

from apps.core.models import (College, Department, DepartmentHeadAssignment, DepartmentInviteAssignment,
                              DeptHeadInvite, FacultyInvite, School, User)
from apps.core.school_scope import school_scope


class DepartmentFoundationTests(TestCase):
    def setUp(self):
        self.school = School.objects.get(code='ADNU')
        self.operator = User.objects.create_user(username='foundation-operator', role='systemadmin')
        self.other = School(name='Other school', code='OTHER')
        self.other.save(actor=self.operator)
        self.college = College.objects.get(school=self.school, code='CCS')
        self.department = Department.objects.get(school=self.school, code='DCS')
        self.second = Department.objects.create(school=self.school, college=self.college,
                                                code='DTEST', name='Department of Test Studies')
        self.other_department = Department.objects.create(school=self.other, code='DCS', name='Department of Computer Science')
        self.head = User.objects.create_user(username='foundation-head', role='depthead', school=self.school, college='CCS')

    def test_department_can_have_no_college_and_school_scope_is_preserved(self):
        with school_scope(self.other):
            department = Department.objects.create(code='DM', name='Department of Mathematics')
            self.assertEqual(department.school_id, self.other.pk)
            self.assertFalse(Department.objects.filter(pk=self.department.pk).exists())

    def test_foreign_school_college_and_forged_department_save_are_rejected(self):
        with self.assertRaises(ValidationError):
            Department.objects.create(school=self.other, college=self.college, code='BAD', name='Invalid')
        with school_scope(self.other), self.assertRaises((PermissionDenied, ValidationError)):
            Department(pk=self.department.pk, school=self.other, code='DCS', name='Forged').save()

    def test_many_heads_and_many_departments_without_duplicates(self):
        other_head = User.objects.create_user(username='foundation-second-head', role='depthead', school=self.school)
        self.head.managed_departments.add(self.department, self.second)
        other_head.managed_departments.add(self.department)
        self.head.managed_departments.add(self.department)
        self.assertEqual(self.head.managed_departments.count(), 2)
        self.assertEqual(self.department.heads.count(), 2)
        self.assertEqual(DepartmentHeadAssignment.objects.count(), 3)

    def test_wrong_role_or_foreign_school_cannot_be_assigned(self):
        faculty = User.objects.create_user(username='foundation-faculty', role='faculty', school=self.school)
        with self.assertRaises(ValidationError), transaction.atomic():
            faculty.managed_departments.add(self.department)
        with self.assertRaises(ValidationError), transaction.atomic():
            self.head.managed_departments.add(self.other_department)
        self.assertFalse(DepartmentHeadAssignment.objects.exists())

    def test_invitation_supports_several_departments_and_checks_school(self):
        invite = DeptHeadInvite.objects.create(email='head@example.invalid', school=self.school, college='CCS')
        invite.departments.add(self.department, self.second)
        self.assertEqual(invite.departments.count(), 2)
        with self.assertRaises(ValidationError), transaction.atomic():
            invite.departments.add(self.other_department)
        with school_scope(self.other):
            self.assertFalse(DepartmentInviteAssignment.objects.exists())

    def test_user_and_faculty_invite_department_require_same_school(self):
        for model, fields in (
            (User, {'username': 'bad-student', 'role': 'student'}),
            (FacultyInvite, {'email': 'bad@example.invalid', 'college': 'CCS'}),
        ):
            with self.subTest(model=model.__name__), self.assertRaises(ValidationError):
                model.objects.create(school=self.school, department=self.other_department, **fields)

    def test_inactive_departments_cannot_receive_new_members_or_heads(self):
        self.second.is_active = False
        self.second.save()
        with self.assertRaises(ValidationError), transaction.atomic():
            self.head.managed_departments.add(self.second)
        with self.assertRaises(ValidationError):
            User.objects.create_user(username='inactive-member', role='student', school=self.school, department=self.second)

    def test_names_and_codes_are_case_insensitively_unique_per_school(self):
        for code, name in (('dcs', 'Different name'), ('DIFFERENT', 'department of computer science')):
            with self.subTest(code=code), self.assertRaises(ValidationError):
                Department.objects.create(school=self.school, code=code, name=name)
        self.assertEqual(self.other_department.code, 'DCS')

    def test_rename_and_same_school_college_grouping_keep_identity(self):
        original_pk = self.department.pk
        self.department.name = 'Department of Computing'
        self.department.college = None
        self.department.save()
        self.assertEqual(self.department.pk, original_pk)
        self.department.code = 'NEW'
        with self.assertRaises(ValidationError):
            self.department.save()

    def test_bulk_and_queryset_writes_cannot_bypass_department_validation(self):
        with self.assertRaises(ValidationError):
            DepartmentHeadAssignment.objects.bulk_create([
                DepartmentHeadAssignment(user=self.head, department=self.other_department),
            ])
        with self.assertRaises(PermissionDenied):
            User.objects.filter(pk=self.head.pk).update(department=self.department)
        with self.assertRaises(PermissionDenied):
            Department.objects.filter(pk=self.department.pk).update(school=self.other)

    def test_database_uniqueness_and_referenced_department_deletion(self):
        DepartmentHeadAssignment.objects.create(user=self.head, department=self.department)
        with self.assertRaises(IntegrityError), transaction.atomic():
            DepartmentHeadAssignment.objects.create(user=self.head, department=self.department)
        with self.assertRaises(ProtectedError):
            self.department.delete()
        with self.assertRaises(ProtectedError):
            self.college.delete()

    def test_forged_related_objects_do_not_bypass_school_or_role_checks(self):
        forged_department = Department(pk=self.other_department.pk, school=self.school, code='DCS')
        with self.assertRaises(ValidationError):
            User.objects.create_user(username='forged-member', role='student', school=self.school,
                                     department=forged_department)
        foreign_head = User.objects.create_user(username='foreign-head', role='depthead', school=self.other)
        forged_head = User(pk=foreign_head.pk, role='depthead', school=self.school)
        with self.assertRaises(ValidationError):
            DepartmentHeadAssignment.objects.create(user=forged_head, department=self.department)
