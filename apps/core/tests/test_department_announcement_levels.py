from unittest.mock import patch

from django.test import RequestFactory, TestCase

from apps.core.forms import CollegeAnnouncementForm
from apps.core.models import CollegeAnnouncement, Department, School, User
from apps.core.school_scope import school_scope
from apps.depthead.views import _department_announcement


class DepartmentAnnouncementLevelsTests(TestCase):
    def setUp(self):
        operator = User.objects.create_user(username='operator', role='systemadmin')
        self.school = School(code='ANNLEVEL', name='Announcement School', educational_levels=['shs', 'college'])
        self.school.save(actor=operator)
        self.head = User.objects.create_user(username='head', role='depthead', school=self.school)
        self.department = Department.objects.create(school=self.school, code='SHS', name='Senior High', student_levels=['shs'])
        self.head.managed_departments.add(self.department)

    def test_settings_form_omits_levels(self):
        self.assertNotIn('student_levels', CollegeAnnouncementForm(school=self.school).fields)

    @patch('apps.depthead.views.send_announcement_email_to_faculty')
    @patch('apps.depthead.views.notify_college_users')
    def test_department_levels_override_posted_levels(self, notify, send):
        for audience, expected in [('students', ['shs']), ('both', ['shs']), ('faculty', [])]:
            with self.subTest(audience=audience):
                request = RequestFactory().post('/', {'department_id':self.department.pk,
                    'message':'Announcement', 'audience':audience, 'student_levels':['college']})
                request.user = self.head
                with school_scope(self.school):
                    response = _department_announcement(request)
                self.assertEqual(response.status_code, 200, response.content)
                self.assertEqual(CollegeAnnouncement.objects.latest('pk').student_levels, expected)
