from unittest.mock import patch

from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase
from django.test import RequestFactory
from django.contrib.messages.storage.fallback import FallbackStorage
from allauth.socialaccount.models import SocialAccount, SocialLogin
from django.urls import reverse

from apps.core.education import LEVEL_CHOICES
from apps.core.models import CollegeAnnouncement, Department, Notification, SchoolChangeLog, User
from apps.core.school_scope import school_scope
from apps.core.services import get_active_announcements
from apps.core.models import OfficeClosure
from apps.core.models import SchoolDomain
from apps.core.adapters import FacSyncSocialAdapter
from apps.faculty.models import FacultyProfile
from apps.superadmin.tests import test_department_management as fixtures


class EducationTests(TestCase):
    def setUp(self):
        fixtures.DepartmentManagementTests.setUp(self)
        with school_scope(self.school):
            self.school.set_educational_levels([key for key, _ in LEVEL_CHOICES], actor=self.admin)
        self.student = User.objects.create_user(username='education-student', role='student', school=self.school)
        self.client.force_login(self.student)
        self.profile_url = reverse('core:student_profile_setup')

    def submit(self, level='college', year='2', department=None, **extra):
        values = {'student_id': 'STUDENT-001', 'educational_level': level, 'year_level': year}
        if department is not None:
            values['department'] = department
        values.update(extra)
        return self.client.post(self.profile_url, values)

    def test_college_profile_derives_college_and_preserves_school_and_role(self):
        response = self.submit(department=self.department.pk, school=self.other.pk, role='superadmin', college='FORGED')
        self.assertEqual(response.status_code, 302)
        self.student.refresh_from_db()
        self.assertEqual(self.student.department_id, self.department.pk)
        self.assertEqual(self.student.college, self.department.college.code)
        self.assertEqual(self.student.school_id, self.school.pk)
        self.assertEqual(self.student.role, 'student')
        self.assertTrue(self.student.profile_completed)
        self.assertEqual(self.student.educational_level, 'college')

    def test_google_registration_assigns_school_then_leaves_level_for_profile_setup(self):
        with school_scope(self.school):
            self.school.set_educational_levels(['jhs'], actor=self.admin)
        SchoolDomain(school=self.school, domain='education-test.edu.ph').save(
            actor=User.objects.get(username='management-operator'))
        request = RequestFactory().get('/accounts/google/login/callback/')
        request.session = {'registration_role': 'student'}
        request._messages = FallbackStorage(request)
        email = 'fresh@education-test.edu.ph'
        login = SocialLogin(user=User(username='fresh-education', email=email), account=SocialAccount(
            provider='google', uid='fresh-education', extra_data={'email': email, 'email_verified': True}))
        adapter = FacSyncSocialAdapter()
        adapter.pre_social_login(request, login)
        def save_user(request, sociallogin, form):
            sociallogin.user.save()
            return sociallogin.user
        with patch('allauth.socialaccount.adapter.DefaultSocialAccountAdapter.save_user', side_effect=save_user):
            saved = adapter.save_user(request, login)
        self.assertEqual(saved.school_id, self.school.pk)
        self.assertEqual(saved.role, 'student')
        self.assertEqual(saved.educational_level, '')
        self.assertIsNone(saved.department_id)
        self.assertFalse(saved.profile_completed)

    def test_basic_levels_use_grade_ranges_and_no_department(self):
        for level, year in [('elementary', '1'), ('elementary', '6'), ('jhs', '7'), ('jhs', '10'), ('shs', '11'), ('shs', '12')]:
            with self.subTest(level=level, year=year):
                self.assertEqual(self.submit(level, year).status_code, 302)
                self.student.refresh_from_db()
                self.assertIsNone(self.student.department_id)
                self.assertIsNone(self.student.college)
                self.assertEqual(self.student.get_year_level_display(), 'Grade ' + year)

    def test_invalid_grades_levels_and_required_id_do_not_complete_profile(self):
        for level, year in [('elementary', '7'), ('jhs', '6'), ('shs', '10'), ('college', '12'), ('college', '0'), ('unknown', '1')]:
            with self.subTest(level=level, year=year):
                response = self.submit(level, year, self.department.pk if level == 'college' else None)
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.context['form'].errors)
        for value in ('', '   ', 'x' * 21):
            self.assertTrue(self.submit(department=self.department.pk, student_id=value).context['form'].errors)
        self.student.refresh_from_db()
        self.assertFalse(self.student.profile_completed)

    def test_foreign_inactive_and_missing_department_are_rejected(self):
        self.second.is_active = False
        self.second.save()
        for target in (self.foreign.pk, self.second.pk, None, 'not-an-id'):
            self.assertIn('department', self.submit(department=target).context['form'].errors)
        self.assertIn('department', self.submit('jhs', '8', self.department.pk).context['form'].errors)

    def test_offered_levels_only_and_single_level_is_preselected(self):
        with school_scope(self.school):
            self.school.set_educational_levels(['college'], actor=self.admin)
        response = self.client.get(self.profile_url)
        self.assertEqual(response.context['form']['educational_level'].value(), 'college')
        self.assertTrue(response.context['form'].fields['educational_level'].widget.is_hidden)
        self.assertNotContains(response, self.foreign.name)
        self.assertIn('educational_level', self.submit('jhs', '8').context['form'].errors)

    def test_college_without_grouping_and_year_six_are_valid(self):
        self.assertEqual(self.submit(year='6', department=self.second.pk).status_code, 302)
        self.student.refresh_from_db()
        self.assertEqual(self.student.department_id, self.second.pk)
        self.assertEqual(self.student.college, '')
        self.assertEqual(self.student.get_year_level_display(), 'Year 6')

    def test_changing_profile_to_basic_clears_previous_college(self):
        self.assertEqual(self.submit(department=self.department.pk).status_code, 302)
        self.assertEqual(self.submit('jhs', '8').status_code, 302)
        self.student.refresh_from_db()
        self.assertIsNone(self.student.department_id)
        self.assertIsNone(self.student.college)

    def test_model_rejects_invalid_basic_assignments_and_years(self):
        self.student.educational_level = 'jhs'
        self.student.year_level = '2'
        with self.assertRaises(ValidationError):
            self.student.save()
        self.student.year_level = '8'
        self.student.department = self.department
        with self.assertRaises(ValidationError):
            self.student.save()

    def test_settings_are_school_bound_audited_and_preserve_identity(self):
        self.client.force_login(self.admin)
        before = self.school.name
        response = self.client.post(reverse('superadmin:school_settings'), {'educational_levels': ['jhs', 'college'],
            'name': 'Forged name', 'school_id': self.other.pk, 'domains': 'forged.edu.ph'})
        self.assertEqual(response.status_code, 200)
        self.school.refresh_from_db()
        self.assertEqual(self.school.name, before)
        self.assertEqual(self.school.educational_levels, ['jhs', 'college'])
        log = SchoolChangeLog.objects.filter(school=self.school, field='educational_levels').first()
        self.assertEqual(log.actor_id, self.admin.pk)
        self.assertEqual(log.new_value, ['jhs', 'college'])
        self.other.refresh_from_db()
        self.assertEqual(self.other.educational_levels, ['college'])

    def test_cannot_remove_used_level_or_submit_empty_invalid_levels(self):
        self.assertEqual(self.submit('jhs', '8').status_code, 302)
        self.client.force_login(self.admin)
        url = reverse('superadmin:school_settings')
        count = SchoolChangeLog.objects.count()
        for levels in (['college'], [], ['not-a-level']):
            response = self.client.post(url, {'educational_levels': levels})
            self.assertEqual(response.status_code, 400)
        self.assertEqual(SchoolChangeLog.objects.count(), count)

    def test_other_roles_cannot_change_school_levels_or_student_profiles(self):
        for role in ('student', 'faculty', 'depthead', 'officeadmin', 'systemadmin'):
            user = User.objects.create_user(username='education-role-' + role, role=role,
                school=None if role == 'systemadmin' else self.school)
            self.client.force_login(user)
            self.assertEqual(self.client.post(reverse('superadmin:school_settings'), {'educational_levels': ['college']}).status_code, 403)
            if role != 'student':
                self.assertEqual(self.client.get(self.profile_url).status_code, 403)
        with school_scope(self.school), self.assertRaises(PermissionDenied):
            self.other.set_educational_levels(['jhs'], actor=self.admin)

    def test_profile_values_are_escaped_on_display(self):
        self.assertEqual(self.submit('shs', '11', student_id='<img src=x>').status_code, 302)
        response = self.client.get(reverse('students:profile'))
        self.assertContains(response, 'Senior High School')
        self.assertContains(response, 'Grade 11')
        self.assertContains(response, '&lt;img src=x&gt;')
        self.assertNotContains(response, '<img src=x>')

    @patch('apps.depthead.views.send_announcement_email_to_faculty')
    def test_announcement_recipient_matrix_and_student_feeds_match(self, email):
        people = {}
        for key, level, year, department in [('college-a', 'college', '2', self.department),
                ('college-b', 'college', '2', self.second), ('elementary', 'elementary', '3', None),
                ('jhs', 'jhs', '8', None), ('shs', 'shs', '11', None)]:
            people[key] = User.objects.create_user(username='announcement-' + key, role='student', school=self.school,
                educational_level=level, year_level=year, department=department)
        self.client.force_login(self.head)
        response = self.client.post(reverse('depthead:create_announcement'), {'department_id': self.department.pk,
            'message': 'Level-specific announcement', 'audience': 'both', 'student_levels': ['jhs', 'college']})
        self.assertEqual(response.status_code, 200, response.content)
        for key, user in people.items():
            expected = key in ('college-a', 'jhs')
            self.assertEqual(Notification.objects.filter(recipient=user).exists(), expected)
            with school_scope(self.school):
                rows = get_active_announcements(audience='students', student=user)
            self.assertEqual(bool(rows), expected)
        self.assertTrue(Notification.objects.filter(recipient=self.faculty).exists())
        foreign = User.objects.create_user(username='foreign-announcement-student', role='student', school=self.other,
            department=self.foreign, educational_level='college', year_level='2')
        self.assertFalse(Notification.objects.filter(recipient=foreign).exists())
        with school_scope(self.other):
            self.assertEqual(get_active_announcements(audience='students', student=foreign), [])
        self.client.force_login(people['jhs'])
        self.assertContains(self.client.get(reverse('students:active_announcements')), 'Level-specific announcement')
        chat = self.client.get(reverse('students:availability_browser_api'), {'metric': 'active_announcements'})
        self.assertEqual(chat.status_code, 200)
        self.assertIn('Level-specific announcement', str(chat.json()))
        # One closed department must not hide available faculty elsewhere in the school.
        OfficeClosure.objects.create(school=self.school, department=self.department, college='CCS', is_closed=True)
        for name, department, college in [('OpenDepartmentTeacher', self.second, ''), ('OpenOfficeTeacher', None, self.office.code)]:
            teacher = User.objects.create_user(username=name, first_name=name, role='faculty', school=self.school,
                department=department, college=college)
            FacultyProfile.objects.create(user=teacher, faculty_id=name, college_id=college, current_status='available')
        available = self.client.get(reverse('students:availability_browser_api'), {'metric': 'available_now'})
        self.assertEqual(available.status_code, 200)
        self.assertIn('OpenDepartmentTeacher', str(available.json()))
        self.assertIn('OpenOfficeTeacher', str(available.json()))

    @patch('apps.depthead.views.send_announcement_email_to_faculty')
    def test_announcement_requires_offered_student_levels_but_faculty_only_does_not(self, email):
        self.client.force_login(self.head)
        url = reverse('depthead:create_announcement')
        for levels in ([], ['unknown']):
            response = self.client.post(url, {'department_id': self.department.pk, 'message': 'Invalid',
                'audience': 'students', 'student_levels': levels})
            self.assertEqual(response.status_code, 400)
        email.assert_not_called()
        response = self.client.post(url, {'department_id': self.department.pk, 'message': 'Faculty only', 'audience': 'faculty'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(CollegeAnnouncement.objects.get(message='Faculty only').student_levels, [])
