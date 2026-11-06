"""Department boundaries with deliberately overlapping college/department codes."""
from datetime import timedelta
import json
from types import SimpleNamespace
from unittest.mock import patch

from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.core.models import CollegeAnnouncement, Department, FacultyInvite, Notification, OfficeClosure, User
from apps.core.school_scope import school_scope
from apps.core.services import get_active_announcements, send_announcement_email_to_faculty
from apps.faculty.models import ConsultationRequest, FacultyProfile, ScheduleEvent, WalkInQueue
from apps.superadmin.tests import test_department_management as management_fixtures
from apps.depthead.scope import DepartmentScope, head_scope
from apps.depthead.models import CollegeAIInsight
from apps.depthead.services.analytics import get_college_analytics
from apps.depthead.services.ai_insights import generate_ai_insights


class DepartmentScopeTests(TestCase):
    def setUp(self):
        management_fixtures.DepartmentManagementTests.setUp(self)
        self.second.college = self.department.college
        self.second.save()
        self.hidden = Department.objects.create(school=self.school, college=self.department.college,
            code='HIDDEN', name='Unassigned same-college department')
        self.head.managed_departments.add(self.second)
        self.student = User.objects.create_user(username='scope-student', role='student', school=self.school, department=self.department, educational_level='college')
        self.profiles = []
        for index, department in enumerate((self.department, self.second, self.hidden, self.foreign)):
            user = User.objects.create_user(username=f'scope-faculty-{index}', first_name=f'ScopeFaculty{index}',
                email=f'scope-faculty-{index}@example.invalid', school=department.school, role='faculty',
                department=department, college='CCS')
            profile = FacultyProfile.objects.create(user=user, faculty_id=f'scope-profile-{index}', college_id='CCS')
            student = self.student if department.school_id == self.school.pk else User.objects.create_user(
                username='foreign-scope-student', role='student', school=self.other)
            ConsultationRequest.objects.create(request_id=f'scope-request-{index}', user=student,
                faculty=profile, date=timezone.localdate(), status='completed')
            WalkInQueue.objects.create(queue_id=f'scope-walk-{index}', user=student, faculty=profile,
                position=1, joined_at=timezone.now())
            self.profiles.append(profile)
        self.client.force_login(self.head)

    def url(self, name, *args):
        return reverse('depthead:' + name, args=args)

    def test_combined_analytics_uses_departments_and_history_snapshots(self):
        with school_scope(self.school):
            data = get_college_analytics(head_scope(self.head))
        self.assertEqual(data['consultations']['total_records'], 2)
        self.assertEqual(data['faculty_availability']['current']['total_active_faculty'], 3)
        self.assertEqual(data['walk_ins']['total'], 2)
        self.assertEqual(data['scope']['scope_type'], 'departments')
        self.assertIn(self.second.name, data['scope']['college_name'])
        self.assertNotIn(self.hidden.name, str(data))
        # A later home change must not rewrite the original consultation scope.
        moved = self.profiles[0].user
        moved.department = self.hidden
        moved.save()
        with school_scope(self.school):
            self.assertEqual(get_college_analytics(head_scope(self.head))['consultations']['total_records'], 2)

    def test_all_head_pages_render_combined_scope_without_other_faculty(self):
        for name in ('admin_dashboard', 'admin_faculty', 'faculty_monitoring', 'faculty_trends',
                     'peak_analytics', 'student_behavior', 'college_settings'):
            with self.subTest(name=name):
                response = self.client.get(self.url(name))
                self.assertEqual(response.status_code, 200, response.content[:300])
                self.assertNotContains(response, 'ScopeFaculty2')
                self.assertNotContains(response, 'ScopeFaculty3')
        dashboard = self.client.get(self.url('admin_dashboard'))
        self.assertEqual(dashboard.context['total_this_month'], 2)
        self.assertContains(dashboard, self.second.name)
        forged_filter = self.client.get(self.url('admin_dashboard'), {'department_id': self.hidden.pk})
        self.assertEqual(forged_filter.context['total_this_month'], 2)
        listing = self.client.get(self.url('admin_faculty'))
        self.assertContains(listing, 'ScopeFaculty0')
        self.assertContains(listing, 'ScopeFaculty1')

    def test_guessed_faculty_ids_cannot_read_write_remove_or_download(self):
        for profile in self.profiles[2:]:
            for name in ('view_faculty_schedule_preview', 'faculty_monitoring_schedule'):
                self.assertEqual(self.client.get(self.url(name, profile.pk)).status_code, 404)
            for name in ('upload_faculty_schedule', 'delete_faculty_schedule'):
                self.assertEqual(self.client.post(self.url(name, profile.pk)).status_code, 404)
            self.assertEqual(self.client.post(self.url('remove_faculty', profile.user_id)).status_code, 404)
            self.assertEqual(self.client.get(self.url('faculty_schedule_template'), {'department_id': profile.user.department_id}).status_code, 404)

    def test_monitoring_and_all_chatbot_questions_exclude_unassigned_names(self):
        from apps.depthead.services.analytics_browser import ANALYTICS_QUESTIONS
        response = self.client.get(self.url('faculty_monitoring_data'))
        self.assertIn('ScopeFaculty1', response.content.decode())
        self.assertNotIn('ScopeFaculty2', response.content.decode())
        for metric in ANALYTICS_QUESTIONS:
            with self.subTest(metric=metric):
                response = self.client.get(self.url('analytics_browser_api'), {'metric': metric})
                self.assertEqual(response.status_code, 200, response.content[:200])
                self.assertNotIn('ScopeFaculty2', response.content.decode())
                self.assertNotIn('ScopeFaculty3', response.content.decode())

    def test_assignment_removal_takes_effect_without_relogin(self):
        self.second.is_active = False
        self.second.save()
        self.assertNotContains(self.client.get(self.url('admin_faculty')), 'ScopeFaculty1')
        self.second.is_active = True
        self.second.save()
        self.head.managed_departments.remove(self.second)
        response = self.client.get(self.url('admin_faculty'))
        self.assertNotContains(response, 'ScopeFaculty1')
        self.assertEqual(self.client.get(self.url('faculty_monitoring_schedule', self.profiles[1].pk)).status_code, 404)
        self.head.managed_departments.clear()
        self.assertEqual(self.client.get(self.url('admin_dashboard')).context['total_this_month'], 0)
        self.assertEqual(self.client.get(self.url('faculty_monitoring_data')).json()['faculty_list'], [])

    @patch('apps.depthead.views.send_faculty_invite_email')
    def test_head_invites_require_an_explicit_assigned_department(self, email):
        for department in (self.hidden, self.foreign):
            response = self.client.post(self.url('invite_faculty'), {'email': 'bad@example.invalid', 'department': department.pk}, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
            self.assertEqual(response.status_code, 400)
        email.assert_not_called()
        response = self.client.post(self.url('invite_faculty'), {'email': 'good@example.invalid', 'department': self.second.pk}, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(response.status_code, 201)
        invite = FacultyInvite.objects.get(email='good@example.invalid')
        self.assertEqual(invite.department_id, self.second.pk)
        self.assertEqual(invite.school_id, self.school.pk)

    @patch('apps.depthead.views.send_announcement_email_to_faculty')
    def test_announcements_only_reach_target_department(self, email):
        for department in (self.hidden, self.foreign):
            self.assertEqual(self.client.post(self.url('create_announcement'), {'department_id': department.pk,
                'message': 'Blocked', 'audience': 'both'}).status_code, 404)
        response = self.client.post(self.url('create_announcement'), {'department_id': self.department.pk,
            'message': '<script>unsafe()</script>', 'audience': 'both', 'student_levels': ['college']})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(Notification.objects.filter(recipient=self.profiles[0].user).exists())
        self.assertFalse(Notification.objects.filter(recipient=self.profiles[1].user).exists())
        self.assertFalse(Notification.objects.filter(recipient=self.profiles[2].user).exists())
        self.assertTrue(Notification.objects.filter(recipient=self.student).exists())
        response = self.client.get(self.url('college_settings'))
        self.assertContains(response, '&lt;script&gt;unsafe()&lt;/script&gt;')

    @patch('apps.core.services._send_html_email')
    def test_announcement_email_recipients_are_department_scoped(self, sender):
        item = CollegeAnnouncement.objects.create(school=self.school, department=self.department,
            college='CCS', posted_by=self.head, message='Test', audience='faculty')
        with school_scope(self.school):
            send_announcement_email_to_faculty(item)
        addresses = [address for call in sender.call_args_list for address in call.args[3]]
        self.assertEqual(addresses, [self.profiles[0].user.email])

    def test_closures_are_independent_inside_same_college(self):
        invalid = self.client.post(self.url('college_settings'), {'department_id': self.second.pk,
            'is_closed': 'on', 'closure_start': 'not-a-date'})
        self.assertEqual(invalid.status_code, 400)
        self.assertFalse(OfficeClosure.objects.filter(department=self.second).exists())
        for department in (self.department, self.second):
            response = self.client.post(self.url('college_settings'), {'department_id': department.pk,
                'is_closed': 'on', 'reason': 'Test closure'})
            self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(OfficeClosure.objects.filter(department__in=[self.department, self.second], is_closed=True).count(), 2)
        self.assertEqual(self.client.post(self.url('college_settings'), {'department_id': self.hidden.pk, 'is_closed': 'on'}).status_code, 404)
        from apps.core.department_access import faculty_closed
        with school_scope(self.school):
            self.assertTrue(faculty_closed(self.profiles[0]))
            self.assertFalse(faculty_closed(self.profiles[2]))

    def test_description_cannot_edit_a_college_or_unassigned_department(self):
        response = self.client.post(self.url('edit_college_description'), {'department_id': self.second.pk,
            'description': 'New description'}, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(response.status_code, 200)
        self.second.refresh_from_db()
        self.assertEqual(self.second.description, 'New description')
        self.assertEqual(self.client.post(self.url('edit_college_description'), {'department_id': self.hidden.pk,
            'description': 'Forged'}).status_code, 404)

    def test_new_records_copy_faculty_department_and_reject_forged_snapshot(self):
        item = ConsultationRequest.objects.get(pk='scope-request-0')
        self.assertEqual(item.department_id, self.department.pk)
        walk = WalkInQueue.objects.get(pk='scope-walk-0')
        self.assertEqual(walk.department_id, self.department.pk)
        with self.assertRaises(ValidationError):
            ConsultationRequest.objects.create(request_id='forged', user=self.student, faculty=self.profiles[0],
                department=self.hidden, date=timezone.localdate())
        # A valid department needs no college for the faculty's own chatbot.
        self.second.college = None
        self.second.save()
        self.profiles[1].user.college = ''
        self.profiles[1].user.save()
        self.profiles[1].college_id = ''
        self.profiles[1].save()
        from apps.faculty.services.consultation_browser import consultation_browser_answer
        with school_scope(self.school):
            result = consultation_browser_answer('consultation_topics', self.profiles[1])
        self.assertTrue(any('1 request' in line for line in result['lines']))

    def test_other_school_cannot_reuse_department_scope(self):
        with school_scope(self.school):
            scope = head_scope(self.head)
        with school_scope(self.other), self.assertRaises(PermissionDenied):
            get_college_analytics(scope)

    @override_settings(GEMINI_API_KEY='synthetic')
    @patch('apps.depthead.services.ai_insights.genai.Client')
    def test_ai_generates_one_combined_insight_and_caches_by_assignment(self, client):
        content = {'summary': 'Combined department report.', 'key_insights': [], 'concerns': [], 'recommendations': []}
        client.return_value.models.generate_content.return_value = SimpleNamespace(parsed=content, text=None)
        with school_scope(self.school):
            CollegeAIInsight.objects.create(school=self.school, college_code='CCS', analytics_hash='legacy',
                insights={**content, 'summary': 'Old college-wide insight'}, model_name='synthetic',
                generated_at=timezone.now(), refresh_after=timezone.now()+timedelta(days=7))
            combined = get_college_analytics(head_scope(self.head))
            result = generate_ai_insights(combined)
            self.assertTrue(result['available'])
            self.assertEqual(result['summary'], 'Combined department report.')
            generate_ai_insights(combined)
            response = self.client.get(self.url('ai_insights_api'))
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()['summary'], 'Combined department report.')
            self.assertEqual(client.return_value.models.generate_content.call_count, 1)
            prompt = client.return_value.models.generate_content.call_args.kwargs['contents']
            self.assertIn('"total_records":2', prompt.replace(' ', ''))
            self.assertNotIn('ScopeFaculty2', prompt)
            self.head.managed_departments.remove(self.second)
            single = get_college_analytics(head_scope(self.head))
            generate_ai_insights(single)
            self.assertEqual(client.return_value.models.generate_content.call_count, 2)
            self.assertNotEqual(combined['scope']['college_code'], single['scope']['college_code'])
            self.assertEqual(CollegeAIInsight.objects.count(), 3)
            # Force the combined entry past its weekly refresh, then generate fresh totals.
            CollegeAIInsight.objects.filter(college_code=combined['scope']['college_code']).update(refresh_after=timezone.now()-timedelta(seconds=1))
            self.head.managed_departments.add(self.second)
            refreshed = get_college_analytics(head_scope(self.head))
            generate_ai_insights(refreshed)
            self.assertEqual(client.return_value.models.generate_content.call_count, 3)

    def test_recipient_reads_do_not_fall_back_to_college(self):
        CollegeAnnouncement.objects.create(school=self.school, department=self.hidden, college='CCS',
            posted_by=self.head, message='Hidden department', audience='both')
        CollegeAnnouncement.objects.create(school=self.school, department=self.department, college='CCS',
            posted_by=self.head, message='Own department', audience='both')
        with school_scope(self.school):
            rows = get_active_announcements('CCS', audience='students', department=self.department)
        self.assertEqual([row['message'] for row in rows], ['Own department'])

    @patch('apps.students.views.refresh_faculty_status')
    @patch('apps.students.views.queue_consultation_email')
    def test_students_can_book_across_departments_but_not_closed_or_foreign_faculty(self, email, refresh):
        self.client.force_login(self.student)
        OfficeClosure.objects.create(school=self.school, department=self.department, college='CCS', is_closed=True)
        day = timezone.localdate() + timedelta(days=3)
        if day.weekday() == 6:
            day += timedelta(days=1)
        payload = {'date': day.isoformat(), 'start_time': '10:00', 'agenda': 'general_concern'}
        url = reverse('students:api_consultation_requests')
        payload['faculty_id'] = self.profiles[0].pk
        self.assertEqual(self.client.post(url, json.dumps(payload), content_type='application/json').status_code, 409)
        payload['faculty_id'] = self.profiles[1].pk
        response = self.client.post(url, json.dumps(payload), content_type='application/json')
        self.assertEqual(response.status_code, 201, response.content)
        item = ConsultationRequest.objects.get(pk=response.json()['request_id'])
        self.assertEqual(item.department_id, self.second.pk)
        self.assertEqual(item.user_id, self.student.pk)
        payload['faculty_id'] = self.profiles[3].pk
        self.assertEqual(self.client.post(url, json.dumps(payload), content_type='application/json').status_code, 404)

    def test_office_admin_keeps_existing_office_scope(self):
        office_admin = User.objects.create_user(username='scope-office-admin', role='officeadmin', school=self.school, college=self.office.code)
        office_user = User.objects.create_user(username='scope-office-faculty', first_name='OfficeFaculty', role='faculty', school=self.school, college=self.office.code)
        FacultyProfile.objects.create(user=office_user, faculty_id='scope-office-profile', college_id=self.office.code)
        self.client.force_login(office_admin)
        response = self.client.get(self.url('admin_faculty'))
        self.assertContains(response, 'OfficeFaculty')
        self.assertNotContains(response, 'ScopeFaculty0')
        self.assertEqual(self.client.get(self.url('college_settings')).status_code, 200)
        self.assertEqual(self.client.get(self.url('admin_dashboard')).status_code, 200)
