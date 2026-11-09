from datetime import date, timedelta, time
from unittest.mock import patch

from django.db.models.deletion import ProtectedError
from django.test import TestCase
from django.urls import reverse

from apps.core.account_lifecycle import consultation_count
from apps.core.models import Department, School, User
from apps.core.school_scope import school_scope
from apps.depthead.scope import DepartmentScope
from apps.depthead.services.analytics import get_base_consultation_queryset
from apps.faculty.models import ConsultationRequest, FacultyProfile


class AccountDeactivationTests(TestCase):
    def setUp(self):
        operator = User.objects.create_user(username='operator', role='systemadmin')
        self.school = School(code='LIFECYCLE', name='Lifecycle school')
        self.school.save(actor=operator)
        self.department = Department.objects.create(school=self.school, code='DCS', name='Department of Computer Science')
        self.admin = User.objects.create_user(username='admin', role='superadmin', school=self.school)
        self.head = User.objects.create_user(username='head', role='depthead', school=self.school)
        self.head.managed_departments.add(self.department)
        self.faculty = User.objects.create_user(username='faculty', email='faculty@school.edu.ph', role='faculty',
                                                school=self.school, department=self.department)
        self.profile = FacultyProfile.objects.create(faculty_id='lifecycle-faculty', user=self.faculty, college_id='')
        self.student = User.objects.create_user(username='student', role='student', school=self.school)
        self.consultation = ConsultationRequest.objects.create(
            request_id='lifecycle-history', faculty=self.profile, user=self.student,
            date=date.today() - timedelta(days=5), start_time=time(9), end_time=time(10), status='completed')
        self.client.force_login(self.admin)

    def url(self, who='faculty'):
        return reverse('superadmin:remove_faculty_superadmin' if who == 'faculty' else 'superadmin:remove_student_superadmin',
                       args=[self.faculty.pk if who == 'faculty' else self.student.pk])

    @patch('apps.core.services.send_faculty_deactivated_email', return_value=True)
    def test_faculty_deactivation_preserves_history_and_sends_once(self, send):
        for _ in range(2):
            self.assertEqual(self.client.post(self.url()).status_code, 200)
        self.faculty.refresh_from_db()
        self.assertEqual(self.faculty.account_status, 'deactivated')
        self.assertFalse(self.faculty.is_active)
        self.assertTrue(FacultyProfile.objects.filter(pk=self.profile.pk).exists())
        self.assertTrue(ConsultationRequest.objects.filter(pk=self.consultation.pk).exists())
        self.assertEqual(send.call_count, 1)
        with school_scope(self.school):
            self.assertEqual(get_base_consultation_queryset(DepartmentScope(self.school.pk, (self.department.pk,), (self.department.name,))).count(), 1)

    @patch('apps.core.services.send_faculty_deactivated_email', side_effect=RuntimeError('mail failed'))
    def test_failed_email_does_not_prevent_deactivation(self, send):
        response = self.client.post(self.url())
        self.assertFalse(response.json()['email_sent'])
        self.faculty.refresh_from_db()
        self.assertFalse(self.faculty.is_active)
        self.assertEqual(consultation_count(self.faculty), 1)

    def test_student_deactivation_and_reactivation_preserve_history(self):
        self.client.post(self.url('student'))
        self.student.refresh_from_db()
        self.assertFalse(self.student.is_active)
        self.assertEqual(consultation_count(self.student), 1)
        self.client.post(self.url('student'), {'action': 'reactivate'})
        self.student.refresh_from_db()
        self.assertTrue(self.student.is_active)
        self.assertEqual(self.student.account_status, 'active')

    def test_hard_deletion_is_protected(self):
        for item in (self.student, self.faculty, self.profile):
            with self.subTest(model=type(item).__name__), self.assertRaises(ProtectedError):
                item.delete()

    @patch('apps.core.services.send_faculty_deactivated_email', return_value=True)
    def test_head_can_only_change_assigned_faculty(self, send):
        self.client.force_login(self.head)
        self.assertEqual(self.client.post(reverse('depthead:remove_faculty', args=[self.faculty.pk])).status_code, 200)
        self.assertEqual(self.client.post(reverse('depthead:remove_faculty', args=[self.faculty.pk]), {'action': 'reactivate'}).status_code, 200)
        other = Department.objects.create(school=self.school, code='OTHER', name='Other department')
        outsider = User.objects.create_user(username='outsider', role='faculty', school=self.school, department=other)
        self.assertEqual(self.client.post(reverse('depthead:remove_faculty', args=[outsider.pk])).status_code, 404)

    def test_student_cannot_change_access(self):
        self.client.force_login(self.student)
        self.assertEqual(self.client.post(self.url()).status_code, 403)

    @patch('apps.core.services.send_faculty_deactivated_email')
    def test_no_email_address_is_silently_skipped(self, send):
        self.faculty.email = ''
        self.faculty.save(update_fields=['email'])
        self.assertEqual(self.client.post(self.url()).status_code, 200)
        send.assert_not_called()

    def test_cross_school_access_is_denied(self):
        operator = User.objects.get(username='operator')
        other = School(code='ELSEWHERE', name='Another school')
        other.save(actor=operator)
        outsider = User.objects.create_user(username='other-school-faculty', role='faculty', school=other)
        self.assertEqual(self.client.post(reverse('superadmin:remove_faculty_superadmin', args=[outsider.pk])).status_code, 404)
        outsider.refresh_from_db()
        self.assertTrue(outsider.is_active)

    def test_deactivated_students_lose_existing_session_access(self):
        from django.test import Client
        student_client = Client()
        student_client.force_login(self.student)
        self.client.post(self.url('student'))
        response = student_client.get(reverse('students:api_consultation_requests'))
        self.assertIn(response.status_code, (302, 403))

    @patch('apps.core.services.send_faculty_deactivated_email', return_value=True)
    def test_deactivated_faculty_not_bookable_or_listed(self, send):
        self.client.post(self.url())
        self.client.force_login(self.student)
        from apps.students.views import _faculty_directory
        with school_scope(self.school):
            self.assertEqual(_faculty_directory(student=self.student), [])
        # A future weekday in the permitted booking window.
        day = date.today() + timedelta(days=3)
        if day.weekday() == 6:
            day += timedelta(days=1)
        response = self.client.post(reverse('students:api_consultation_requests'),
                                    {'faculty_id': self.profile.pk, 'date': day.isoformat(),
                                     'start_time': '09:00', 'agenda': 'general_concern'}, content_type='application/json')
        self.assertEqual(response.status_code, 404)
        self.assertEqual(ConsultationRequest.objects.count(), 1)

    def test_count_and_preservation_warning_are_rendered(self):
        for route in ('superadmin:manage_faculty', 'superadmin:manage_students'):
            response = self.client.get(reverse(route))
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, 'Deactivate')
            if route.endswith('manage_faculty'):
                self.assertContains(response, '1 consultation record(s) will be preserved')
            else:
                self.assertContains(response, 'data-history-count="1"')
