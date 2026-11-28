from unittest.mock import patch

from allauth.socialaccount.models import SocialAccount, SocialLogin
from django.contrib.messages.storage.fallback import FallbackStorage
from django.test import RequestFactory, TestCase
from django.urls import reverse

from apps.core.adapters import FacSyncSocialAdapter
from apps.core.models import Department, DeptHeadInvite, Office, OfficeAdminInvite, School, User, UserRole
from apps.depthead.forms import FacultyInviteForm
from apps.faculty.models import FacultyProfile
from apps.schooladmin.forms import DeptHeadInviteForm, OfficeAdminInviteForm


class AdminFacultySetupTests(TestCase):
    def test_department_count_depends_on_title(self):
        from apps.schooladmin.forms import HeadAssignmentForm
        from apps.core.models import College
        college = College.objects.create(school=self.school, code='SCI', name='Science')
        self.department.college = college
        self.department.save()
        second = Department.objects.create(school=self.school, college=college, code='MA', name='Math', student_levels=['college'])
        data = {'email':'head@example.com', 'educational_level':'college',
                'departments':[self.department.pk, second.pk]}
        for form_class in (DeptHeadInviteForm, HeadAssignmentForm):
            for title, valid in [('chairperson', False), ('dean', True)]:
                with self.subTest(form=form_class, title=title):
                    payload = {**data, 'title':title}
                    if title == 'dean':
                        payload['assigned_college'] = college.pk
                        payload.pop('departments')
                    form = form_class(data=payload, school=self.school)
                    self.assertEqual(form.is_valid(), valid, form.errors)
                    if valid:
                        self.assertEqual({d.pk for d in form.cleaned_data['departments']}, {self.department.pk, second.pk})

    def setUp(self):
        operator = User.objects.create_user(username='operator', role='systemadmin')
        self.school = School(code='SETUP', name='Setup school')
        self.school.save(actor=operator)
        self.department = Department.objects.create(school=self.school, code='CS', name='Computing', student_levels=['college'])
        self.office = Office.objects.create(school=self.school, code='REG', name='Registrar')

    def test_invitation_forms_accept_no_faculty_id(self):
        head = DeptHeadInviteForm(data={'email':'head@example.com', 'educational_level':'college', 'title':'chairperson',
            'departments':[self.department.pk], 'include_faculty_access':'on'}, school=self.school)
        office = OfficeAdminInviteForm(data={'email':'office@example.com', 'office':'REG'}, school=self.school)
        self.assertNotIn('faculty_id', FacultyInviteForm(school=self.school).fields)
        for form in (head, office):
            self.assertNotIn('faculty_id', form.fields)
            self.assertTrue(form.is_valid(), form.errors)

    def test_combined_invitations_defer_profile_creation_including_old_invites(self):
        for model in (DeptHeadInvite, OfficeAdminInvite):
            for old_id in ('', 'LEGACY-ID'):
                with self.subTest(model=model, old_id=old_id):
                    email = f'{model.__name__}{old_id}@example.com'.lower()
                    kwargs = dict(school=self.school, email=email, faculty_id=old_id)
                    if model == DeptHeadInvite:
                        kwargs.update(include_faculty_access=True, faculty_department=self.department, title='chairperson', college='')
                    else:
                        kwargs['office'] = 'REG'
                        kwargs['include_faculty_access'] = True
                    invite = model.objects.create(**kwargs)
                    if model == DeptHeadInvite:
                        invite.departments.add(self.department)
                    user = User(username=email, email=email, school=self.school,
                        role='depthead' if model == DeptHeadInvite else 'officeadmin', college='REG')
                    login = SocialLogin(user=user, account=SocialAccount(provider='google', uid=email,
                        extra_data={'email':email, 'email_verified':True}))
                    login._facsync_invite = invite
                    request = RequestFactory().get('/')
                    request.session = {}
                    request._messages = FallbackStorage(request)
                    def save(*args, **kwargs):
                        user.save()
                        return user
                    with patch('allauth.socialaccount.adapter.DefaultSocialAccountAdapter.save_user', side_effect=save):
                        saved = FacSyncSocialAdapter().save_user(request, login)
                    self.assertFalse(FacultyProfile.objects.filter(user=saved).exists())
                    self.assertFalse(saved.profile_completed)
                    self.assertTrue(saved.role_assignments.filter(role='faculty', is_active=True).exists())
                    self.assertTrue(request.session['faculty_profile_setup_allowed'])

    def test_setup_required_and_existing_profile_reused(self):
        user = User.objects.create_user(username='office-user', role='officeadmin', school=self.school, college='REG')
        self.client.force_login(user)
        self.assertRedirects(self.client.get(reverse('faculty:dashboard')), reverse('core:faculty_profile_setup'), fetch_redirect_response=False)
        response = self.client.post(reverse('core:faculty_profile_setup'), {'faculty_id':'', 'office_location':''})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(FacultyProfile.objects.filter(user=user).exists())
        other = User.objects.create_user(username='existing-faculty', role='faculty', school=self.school)
        FacultyProfile.objects.create(user=other, faculty_id='TAKEN', college_id='')
        response = self.client.post(reverse('core:faculty_profile_setup'), {'faculty_id':'TAKEN', 'office_location':'Room 1'})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(FacultyProfile.objects.filter(user=user).exists())
        response = self.client.post(reverse('core:faculty_profile_setup'), {'faculty_id':'MY-ID', 'office_location':'Room 1'})
        self.assertEqual(response.status_code, 302)
        profile = FacultyProfile.objects.get(user=user)
        self.assertEqual(profile.pk, 'MY-ID')
        self.client.post(reverse('core:faculty_profile_setup'), {'faculty_id':'OTHER', 'office_location':'Room 2'})
        profile.refresh_from_db()
        self.assertEqual(profile.office_location, 'Room 1')
        self.assertEqual(FacultyProfile.objects.filter(user=user).count(), 1)

    def test_existing_admin_enters_faculty_id_during_own_setup(self):
        from apps.depthead.faculty_access import add_faculty_access

        actor = User.objects.create_user(
            username='office-head', role='officeadmin', school=self.school, college=self.office.code,
        )
        admin = User.objects.create_user(
            username='admin-without-faculty', role='officeadmin', school=self.school, college=self.office.code,
        )
        UserRole.objects.create(user=admin, role='faculty', is_active=False, assigned_by=actor)

        add_faculty_access(actor, admin.pk)

        self.assertTrue(admin.role_assignments.get(role='faculty').is_active)
        self.assertFalse(FacultyProfile.objects.filter(user=admin).exists())
        self.client.force_login(admin)
        self.assertRedirects(
            self.client.get(reverse('faculty:dashboard')),
            reverse('core:faculty_profile_setup'),
            fetch_redirect_response=False,
        )

        response = self.client.post(reverse('core:faculty_profile_setup'), {
            'faculty_id': 'SELF-ENTERED-ID',
            'office_location': 'Registrar Office',
        })

        self.assertRedirects(response, reverse('faculty:dashboard'), fetch_redirect_response=False)
        self.assertTrue(FacultyProfile.objects.filter(user=admin, faculty_id='SELF-ENTERED-ID').exists())

    @patch('apps.depthead.views.send_faculty_role_added_email', return_value=True)
    def test_department_head_can_add_existing_admin_without_faculty_id(self, send_email):
        actor = User.objects.create_user(
            username='department-head', role='depthead', title='chairperson',
            school=self.school, college='',
        )
        self.department.heads.add(actor)
        admin = User.objects.create_user(
            username='existing-admin', email='existing-admin@example.com',
            role='depthead', title='chairperson', school=self.school,
            college='',
        )
        self.department.heads.add(admin)
        self.client.force_login(actor)

        response = self.client.post(
            reverse('depthead:invite_faculty'),
            {'email': admin.email, 'department': self.department.pk},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(response.json()['existing_account'])
        self.assertTrue(admin.role_assignments.get(role='faculty').is_active)
        self.assertFalse(FacultyProfile.objects.filter(user=admin).exists())
        send_email.assert_called_once_with(admin, self.department.name, needs_setup=True)

    @patch('apps.depthead.views.send_faculty_role_added_email', return_value=True)
    def test_restoring_access_reuses_existing_faculty_profile(self, send_email):
        actor = User.objects.create_user(
            username='restoring-office-head', role='officeadmin',
            school=self.school, college=self.office.code,
        )
        admin = User.objects.create_user(
            username='admin-with-profile', email='profile-admin@example.com', role='officeadmin',
            school=self.school, college=self.office.code,
        )
        UserRole.objects.create(user=admin, role='faculty', is_active=False, assigned_by=actor)
        profile = FacultyProfile.objects.create(
            user=admin, faculty_id='PRESERVED-ID', college_id=self.office.code,
            office_location='Original office',
        )

        self.client.force_login(actor)
        response = self.client.post(
            reverse('depthead:invite_faculty'),
            {'email': admin.email},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        self.assertEqual(response.status_code, 200, response.content)
        self.assertNotIn('enter their Faculty ID', response.json()['message'])
        self.assertTrue(admin.role_assignments.get(role='faculty').is_active)
        self.assertEqual(FacultyProfile.objects.get(user=admin).pk, profile.pk)
        self.assertEqual(FacultyProfile.objects.filter(user=admin).count(), 1)
        send_email.assert_called_once_with(admin, self.office.name, needs_setup=False)

    def test_office_only_invite_has_admin_access_without_faculty_setup(self):
        form = OfficeAdminInviteForm(data={'email':'adminonly@example.com', 'office':'REG'}, school=self.school)
        self.assertTrue(form.is_valid(), form.errors)
        invite = form.save()
        self.assertFalse(invite.include_faculty_access)
        user = User(username='adminonly', email=invite.email, school=self.school, role='officeadmin', college='REG')
        login = SocialLogin(user=user, account=SocialAccount(provider='google', uid='adminonly',
            extra_data={'email':invite.email, 'email_verified':True}))
        login._facsync_invite = invite
        request = RequestFactory().get('/')
        request.session = {}
        request._messages = FallbackStorage(request)
        def save(*args, **kwargs):
            user.save()
            return user
        with patch('allauth.socialaccount.adapter.DefaultSocialAccountAdapter.save_user', side_effect=save):
            saved = FacSyncSocialAdapter().save_user(request, login)
        self.assertTrue(saved.profile_completed)
        self.assertNotIn('faculty_profile_setup_allowed', request.session)
        self.assertFalse(FacultyProfile.objects.filter(user=saved).exists())
        from apps.core.role_access import available_roles, can_access_role
        self.assertEqual(available_roles(saved), [('officeadmin', 'Office Admin')])
        self.assertTrue(can_access_role(saved, 'depthead'))
        self.assertFalse(can_access_role(saved, 'faculty'))
        self.client.force_login(saved)
        self.assertEqual(self.client.get(reverse('faculty:dashboard')).status_code, 403)
        self.assertEqual(self.client.get(reverse('core:faculty_profile_setup')).status_code, 403)
        self.assertRedirects(self.client.get(reverse('core:post_login_redirect')), reverse('depthead:admin_dashboard'), fetch_redirect_response=False)
        self.assertEqual(self.client.get(reverse('depthead:admin_dashboard')).status_code, 200)
