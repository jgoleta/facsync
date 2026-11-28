from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.core.models import College, Department, School
from apps.faculty.models import FacultyProfile


class FacultyDirectoryDeletionRaceTests(TestCase):
    def setUp(self):
        users = get_user_model()
        operator = users.objects.create_user(username='directory-race-operator', role='systemadmin')
        self.school = School(code='DIRECTORYRACE', name='Directory Race School')
        self.school.save(actor=operator)
        college = College.objects.create(school=self.school, code='SCI', name='Science')
        department = Department.objects.create(
            school=self.school,
            college=college,
            code='BIO',
            name='Biology',
            student_levels=['college'],
        )
        self.student = users.objects.create_user(
            username='directory-race-student',
            password='test-password',
            role='student',
            school=self.school,
            educational_level='college',
            year_level='1',
            student_id='STUDENT-1',
            department=department,
            college=college.code,
            profile_completed=True,
        )
        for faculty_id in ('deleted-during-refresh', 'remaining-faculty'):
            user = users.objects.create_user(
                username=faculty_id,
                role='faculty',
                school=self.school,
                department=department,
                college=college.code,
                account_status='active',
            )
            FacultyProfile.objects.create(
                faculty_id=faculty_id,
                user=user,
                college_id=college.code,
            )
        self.client.force_login(self.student)

    def test_profile_deleted_during_refresh_is_skipped(self):
        def refresh(profile):
            if profile.pk == 'deleted-during-refresh':
                raise FacultyProfile.DoesNotExist

        with patch('apps.students.views.refresh_faculty_status', side_effect=refresh):
            response = self.client.get(reverse('students:api_faculty_statuses'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [item['faculty_id'] for item in response.json()['faculty']],
            ['remaining-faculty'],
        )
