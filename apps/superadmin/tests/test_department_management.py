from unittest.mock import patch

from allauth.core.exceptions import ImmediateHttpResponse
from allauth.socialaccount.models import SocialAccount, SocialLogin
from django.contrib.messages.storage.fallback import FallbackStorage
from django.test import RequestFactory, TestCase
from django.urls import reverse

from apps.core.adapters import FacSyncSocialAdapter
from apps.core.models import College, Department, DeptHeadInvite, FacultyInvite, Office, School, User
from apps.faculty.models import ConsultationRequest, FacultyProfile


class DepartmentManagementTests(TestCase):
    def setUp(self):
        self.school = School.objects.get(code='ADNU')
        self.admin = User.objects.create_user(username='management-admin', role='superadmin', school=self.school)
        operator = User.objects.create_user(username='management-operator', role='systemadmin')
        self.other = School(code='OTHER', name='Other school')
        self.other.save(actor=operator)
        self.department = Department.objects.get(school=self.school, code='DCS')
        self.second = Department.objects.create(school=self.school, code='DTEST', name='Department of Test Studies')
        self.foreign = Department.objects.create(school=self.other, code='DCS', name='Other department')
        self.head = User.objects.create_user(username='management-head', role='depthead', school=self.school, title='dean', email='head@example.invalid')
        self.head.managed_departments.add(self.department)
        self.faculty = User.objects.create_user(username='management-faculty', role='faculty', school=self.school,
                                                department=self.department, college='CCS')
        self.profile = FacultyProfile.objects.create(user=self.faculty, faculty_id='management-faculty', college_id='CCS')
        self.office = Office.objects.create(school=self.school, code='GUIDANCE', name='Guidance Office')
        self.client.force_login(self.admin)

    def post(self, name, data=None, args=None):
        return self.client.post(reverse('superadmin:' + name, args=args), data or {}, HTTP_X_REQUESTED_WITH='XMLHttpRequest')

    def test_pages_render_assignments_avatars_and_active_navigation(self):
        for name in ('manage_departments', 'manage_admins', 'manage_faculty'):
            response = self.client.get(reverse('superadmin:' + name))
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, 'Manage Departments')
            self.assertContains(response, 'aria-current="page"')
            self.assertNotContains(response, self.foreign.name)
        response = self.client.get(reverse('superadmin:manage_admins'))
        self.assertContains(response, 'Department of Computer Science')
        self.assertContains(response, 'College Head')
        self.assertContains(response, 'fs-avatar-table')
        self.assertContains(response, 'Head Invitations')

    def test_department_create_rename_optional_college_and_locked_code(self):
        response = self.post('create_department', {'name': 'Department of Mathematics', 'code': 'dm', 'college': '', 'description': 'Test'})
        self.assertEqual(response.status_code, 200, response.content)
        item = Department.objects.get(school=self.school, code='DM')
        self.assertIsNone(item.college_id)
        response = self.post('edit_department', {'name': 'Department of Applied Mathematics', 'code': 'FORGED', 'college': self.department.college_id, 'description': ''}, [item.pk])
        self.assertEqual(response.status_code, 200, response.content)
        item.refresh_from_db()
        self.assertEqual(item.code, 'DM')
        self.assertEqual(item.college_id, self.department.college_id)

    def test_duplicate_invalid_and_foreign_college_errors(self):
        college = College.objects.create(school=self.other, code='CCS', name='Foreign college')
        for values in ({'name': '', 'code': 'X'}, {'name': 'Other', 'code': 'DCS'},
                       {'name': 'Other', 'code': 'DM', 'college': college.pk}):
            with self.subTest(values=values):
                response = self.post('create_department', values)
                self.assertEqual(response.status_code, 400)
                self.assertTrue(response.json()['error'])

    def test_deactivate_reactivate_empty_and_preserve_protected_department(self):
        self.assertEqual(self.post('department_status', {'action': 'deactivate'}, [self.second.pk]).status_code, 200)
        self.second.refresh_from_db()
        self.assertFalse(self.second.is_active)
        self.assertEqual(self.post('department_status', {'action': 'reactivate'}, [self.second.pk]).status_code, 200)
        self.assertEqual(self.post('department_status', {'action': 'deactivate'}, [self.department.pk]).status_code, 409)
        self.assertEqual(self.post('delete_department', args=[self.department.pk]).status_code, 409)
        self.assertEqual(self.post('delete_department', args=[self.second.pk]).status_code, 200)

    def test_pending_invitation_prevents_department_deactivation(self):
        invite = DeptHeadInvite.objects.create(school=self.school, email='pending@example.invalid', title='dean', college='')
        invite.departments.add(self.second)
        self.assertEqual(self.post('department_status', {'action': 'deactivate'}, [self.second.pk]).status_code, 409)

    def test_foreign_ids_and_all_non_superadmin_roles_are_rejected(self):
        self.assertEqual(self.post('delete_department', args=[self.foreign.pk]).status_code, 404)
        self.assertEqual(self.post('department_status', {'action': 'deactivate'}, [self.foreign.pk]).status_code, 404)
        foreign_head = User.objects.create_user(username='foreign-head', school=self.other, role='depthead')
        foreign_faculty = User.objects.create_user(username='foreign-faculty', school=self.other, role='faculty')
        self.assertEqual(self.post('edit_depthead', {'title': 'dean', 'departments': [self.second.pk],
            'account_status': 'active'}, [foreign_head.pk]).status_code, 404)
        self.assertEqual(self.post('assign_faculty', {'unit': f'department:{self.second.pk}'},
            [foreign_faculty.pk]).status_code, 404)
        for role in ('student', 'faculty', 'depthead', 'officeadmin', 'systemadmin'):
            user = User.objects.create_user(username='forbidden-' + role, role=role,
                                             school=None if role == 'systemadmin' else self.school)
            self.client.force_login(user)
            for name, data, args in (
                ('create_department', {'name': 'Invalid', 'code': 'XX'}, None),
                ('department_status', {'action': 'deactivate'}, [self.second.pk]),
                ('delete_department', {}, [self.second.pk]),
                ('edit_depthead', {}, [self.head.pk]),
                ('assign_faculty', {'unit': f'department:{self.second.pk}'}, [self.faculty.pk]),
                ('invite_depthead', {}, None),
            ):
                with self.subTest(role=role, name=name):
                    self.assertEqual(self.post(name, data, args).status_code, 403)

    @patch('apps.superadmin.views.send_depthead_invite_email')
    def test_head_invite_multiple_departments_and_edit_are_saved(self, email):
        response = self.post('invite_depthead', {'email': 'new-head@example.invalid', 'departments': [self.department.pk, self.second.pk], 'title': 'dean'})
        self.assertEqual(response.status_code, 200, response.content)
        invite = DeptHeadInvite.objects.get(email='new-head@example.invalid')
        self.assertEqual(invite.departments.count(), 2)
        self.assertEqual(invite.school_id, self.school.pk)
        self.assertEqual(email.call_args.args[0], invite.email)
        self.assertIn(self.second.name, email.call_args.args[1])
        response = self.post('edit_head_invite', {'email': invite.email, 'departments': [self.second.pk], 'title': 'chairperson'}, [invite.pk])
        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(invite.departments.values_list('pk', flat=True)), [self.second.pk])

    @patch('apps.superadmin.views.send_depthead_invite_email', side_effect=RuntimeError('synthetic failure'))
    def test_failed_email_does_not_undo_head_invite(self, email):
        response = self.post('invite_depthead', {'email': 'email-failure@example.invalid', 'departments': [self.second.pk], 'title': 'dean'})
        self.assertTrue(response.json()['success'])
        self.assertFalse(response.json()['email_sent'])
        self.assertTrue(DeptHeadInvite.objects.filter(email='email-failure@example.invalid').exists())

    def test_head_assignments_multiple_shared_titles_and_deactivation_transition(self):
        values = {'departments': [self.department.pk, self.second.pk], 'title': 'dean', 'account_status': 'active'}
        self.assertEqual(self.post('edit_depthead', values, [self.head.pk]).status_code, 200)
        self.assertEqual(self.head.managed_departments.count(), 2)
        other = User.objects.create_user(username='shared-head', role='depthead', school=self.school)
        self.assertEqual(self.post('edit_depthead', {'departments': [self.department.pk], 'title': 'chairperson', 'account_status': 'active'}, [other.pk]).status_code, 200)
        self.assertEqual(self.department.heads.count(), 2)
        with patch('apps.superadmin.views.send_depthead_deactivated_email') as email:
            for status in ('deactivated', 'deactivated', 'active'):
                values['account_status'] = status
                self.assertEqual(self.post('edit_depthead', values, [self.head.pk]).status_code, 200)
            email.assert_called_once()

    def test_invalid_head_assignments_do_not_clear_previous_assignments(self):
        for ids in ([], [self.foreign.pk], ['not-an-id']):
            response = self.post('edit_depthead', {'departments': ids, 'title': 'dean', 'account_status': 'active'}, [self.head.pk])
            self.assertEqual(response.status_code, 400)
            self.assertEqual(list(self.head.managed_departments.values_list('pk', flat=True)), [self.department.pk])

    @patch('apps.superadmin.views.send_faculty_invite_email')
    def test_faculty_invites_support_departments_and_existing_offices(self, email):
        for suffix, unit, department, college in (
            ('academic', f'department:{self.second.pk}', self.second.pk, ''),
            ('office', f'office:{self.office.pk}', None, 'GUIDANCE'),
        ):
            response = self.post('invite_faculty_superadmin', {'email': suffix + '@example.invalid', 'unit': unit})
            self.assertEqual(response.status_code, 201, response.content)
            invite = FacultyInvite.objects.get(email=suffix + '@example.invalid')
            self.assertEqual(invite.department_id, department)
            self.assertEqual(invite.college, college)
        email.side_effect = RuntimeError('synthetic failure')
        response = self.post('invite_faculty_superadmin', {'email': 'faculty-mail-failure@example.invalid',
            'unit': f'department:{self.second.pk}'})
        self.assertEqual(response.status_code, 201)
        self.assertFalse(response.json()['email_sent'])
        self.assertTrue(FacultyInvite.objects.filter(email='faculty-mail-failure@example.invalid', department=self.second).exists())

    def test_foreign_and_inactive_faculty_targets_are_rejected(self):
        self.second.is_active = False
        self.second.save()
        for unit in (f'department:{self.foreign.pk}', f'department:{self.second.pk}', 'department:-1', 'unknown:1'):
            self.assertEqual(self.post('assign_faculty', {'unit': unit}, [self.faculty.pk]).status_code, 400)
        self.faculty.refresh_from_db()
        self.assertEqual(self.faculty.department_id, self.department.pk)

    def test_faculty_assignment_updates_legacy_profile_without_changing_identifier(self):
        response = self.post('assign_faculty', {'unit': f'department:{self.second.pk}'}, [self.faculty.pk])
        self.assertEqual(response.status_code, 200, response.content)
        self.faculty.refresh_from_db(); self.profile.refresh_from_db()
        self.assertEqual(self.faculty.department_id, self.second.pk)
        self.assertEqual(self.profile.pk, 'management-faculty')
        self.assertEqual(self.profile.college_id, '')

    def test_history_blocks_transfers_but_allows_keeping_same_department(self):
        student = User.objects.create_user(username='history-student', role='student', school=self.school)
        item = ConsultationRequest.objects.create(request_id='preserved-history', faculty=self.profile, user=student,
            date='2026-11-10', status='completed', department=self.department)
        self.assertEqual(self.post('assign_faculty', {'unit': f'department:{self.second.pk}'}, [self.faculty.pk]).status_code, 409)
        self.assertEqual(self.post('assign_faculty', {'unit': f'department:{self.department.pk}'}, [self.faculty.pk]).status_code, 200)
        item.refresh_from_db()
        self.assertEqual(item.department_id, self.department.pk)

    def test_protected_college_deletion_displays_message(self):
        listing = self.client.get(reverse('superadmin:manage_colleges'))
        self.assertContains(listing, self.department.name)
        self.assertContains(listing, '<th>Departments</th>', html=True)
        response = self.client.post(reverse('superadmin:delete_college', args=[self.department.college_id]), follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Reassign those departments')

    def login_data(self, email):
        request = RequestFactory().get('/accounts/google/login/callback/')
        request.session = {}
        request._messages = FallbackStorage(request)
        login = SocialLogin(user=User(username='activated-' + email.split('@')[0], email=email),
            account=SocialAccount(provider='google', uid=email, extra_data={'email': email, 'email_verified': True}))
        return request, login

    def test_first_login_copies_head_assignments_before_deleting_invite(self):
        invite = DeptHeadInvite.objects.create(school=self.school, email='activation@example.invalid', title='dean', college='CCS')
        invite.departments.add(self.department, self.second)
        request, login = self.login_data(invite.email)
        adapter = FacSyncSocialAdapter()
        adapter.pre_social_login(request, login)
        def save_user(request, sociallogin, form):
            sociallogin.user.save()
            return sociallogin.user
        with patch('allauth.socialaccount.adapter.DefaultSocialAccountAdapter.save_user', side_effect=save_user):
            saved = adapter.save_user(request, login)
        self.assertEqual(saved.role, 'depthead')
        self.assertEqual(saved.school_id, self.school.pk)
        self.assertEqual(saved.managed_departments.count(), 2)
        self.assertFalse(DeptHeadInvite.objects.filter(pk=invite.pk).exists())

    def test_first_login_uses_latest_saved_faculty_department(self):
        invite = FacultyInvite.objects.create(school=self.school, email='faculty-activation@example.invalid', college='CCS', department=self.department)
        request, login = self.login_data(invite.email)
        adapter = FacSyncSocialAdapter(); adapter.pre_social_login(request, login)
        invite.department = self.second; invite.college = ''; invite.save()
        def save_user(request, sociallogin, form):
            sociallogin.user.save()
            return sociallogin.user
        with patch('allauth.socialaccount.adapter.DefaultSocialAccountAdapter.save_user', side_effect=save_user):
            saved = adapter.save_user(request, login)
        self.assertEqual(saved.department_id, self.second.pk)
        self.assertEqual(saved.college, '')
        self.assertFalse(FacultyInvite.objects.filter(pk=invite.pk).exists())

    def test_inactive_invited_department_denies_activation(self):
        invite = DeptHeadInvite.objects.create(school=self.school, email='inactive-activation@example.invalid', title='dean', college='')
        invite.departments.add(self.second)
        request, login = self.login_data(invite.email)
        adapter = FacSyncSocialAdapter(); adapter.pre_social_login(request, login)
        self.second.is_active = False; self.second.save()
        with self.assertRaises(ImmediateHttpResponse):
            adapter.save_user(request, login)
        self.assertTrue(DeptHeadInvite.objects.filter(pk=invite.pk).exists())

    def test_missing_departments_and_forged_invite_targets_do_not_send_email(self):
        with patch('apps.superadmin.views.send_depthead_invite_email') as email:
            for departments in ([], [self.foreign.pk]):
                self.assertEqual(self.post('invite_depthead', {'email':'invalid-invite@example.invalid', 'title':'dean', 'departments':departments}).status_code, 400)
            email.assert_not_called()
