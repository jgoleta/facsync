"""Two real tenant fixtures with colliding college codes; no default tenant."""
from datetime import time, timedelta
import json
from unittest.mock import patch
from types import SimpleNamespace

from django.core import mail
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase, RequestFactory, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.core.models import (
    College, CollegeAnnouncement, DeptHeadInvite, FacultyInvite, Notification,
    OfficeClosure, School, User,
)
from apps.core.school_scope import ALL_SCHOOLS, current_school, school_scope
from apps.core.services import notify_college_users, send_announcement_email_to_faculty, notify_faculty_status_subscribers
from apps.depthead.models import CollegeAIInsight
from apps.depthead.services.analytics import get_college_analytics, get_base_consultation_queryset
from apps.depthead.services.analytics_browser import ANALYTICS_QUESTIONS
from apps.depthead.services.ai_insights import generate_ai_insights, get_stored_ai_insights
from apps.faculty.models import (
    ConsultationRequest, FacultyProfile, ScheduleEvent, StatusHistory,
    StatusEmailDelivery, WalkInQueue,
)
from apps.faculty.services.consultation_browser import QUESTIONS as FACULTY_QUESTIONS
from apps.students.availability_browser import QUESTIONS as STUDENT_QUESTIONS
from apps.students.models import FacultyStatusSubscription
from apps.core.adapters import FacSyncSocialAdapter
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from allauth.core.exceptions import ImmediateHttpResponse
from django.contrib.messages.storage.fallback import FallbackStorage


class SchoolIsolationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.operator = User.objects.create_user(username='operator', role='systemadmin', is_staff=True, is_superuser=True)
        cls.adnu = School.objects.get(code='ADNU')
        cls.unc = School(code='UNC', name='University of Nueva Caceres')
        cls.unc.save(actor=cls.operator)
        cls.unc_college = College.objects.create(school=cls.unc, code='CCS', name='UNC_PRIVATE_COLLEGE')
        cls.data = {}
        now = timezone.now()
        for school in (cls.adnu, cls.unc):
            marker = school.code + '_PRIVATE_'
            users = {}
            for role in ('superadmin', 'depthead', 'faculty', 'student'):
                users[role] = User.objects.create_user(
                    username=marker + role, first_name=marker + role,
                    email=school.code.lower() + '.' + role + '@example.invalid',
                    role=role, school=school, college='CCS', profile_completed=True,
                )
            faculty = FacultyProfile.objects.create(
                user=users['faculty'], faculty_id=marker + 'faculty', college_id='CCS',
                current_status='available', manual_status='available', manual_status_override=True,
                sync_enabled=False, walk_ins_enabled=True,
            )
            event = ScheduleEvent.objects.create(
                faculty=faculty, title=marker + 'EVENT', date=now.date() + timedelta(days=2),
                start_time=time(9), end_time=time(10),
            )
            consultation = ConsultationRequest.objects.create(
                request_id=marker + 'CONSULTATION', user=users['student'], faculty=faculty,
                date=now.date(), start_time=time(13), end_time=time(14), status='approved',
                student_message=marker + 'MESSAGE', faculty_note=marker + 'NOTE',
            )
            queue = WalkInQueue.objects.create(queue_id=marker + 'QUEUE', user=users['student'],
                faculty=faculty, position=1, joined_at=now, status='waiting')
            history = StatusHistory.objects.create(history_id=marker + 'HISTORY', faculty=faculty,
                status='available', changed_at=now)
            subscription = FacultyStatusSubscription.objects.create(student=users['student'], faculty=faculty)
            announcement = CollegeAnnouncement.objects.create(school=school, college='ccs', audience='both',
                message=marker + 'ANNOUNCEMENT', posted_by=users['depthead'], expiry=now + timedelta(days=7))
            closure = OfficeClosure.objects.create(school=school, college='CCS', is_closed=school == cls.adnu,
                reason=marker + 'CLOSURE', updated_by=users['depthead'])
            notification = Notification.objects.create(recipient=users['student'], notification_type='announcement',
                title=marker + 'NOTIFICATION', message=marker + 'NOTIFICATION_MESSAGE')
            insight = CollegeAIInsight.objects.create(school=school, college_code='CCS', analytics_hash='0' * 64,
                insights={'available': True, 'summary': marker + 'AI', 'key_insights': [], 'concerns': [], 'recommendations': []},
                model_name='test', generated_at=now, refresh_after=now + timedelta(days=7))
            cls.data[school.code] = dict(users=users, faculty=faculty, event=event, consultation=consultation,
                queue=queue, history=history, subscription=subscription, announcement=announcement,
                closure=closure, notification=notification, insight=insight)

    def login(self, role, code='UNC'):
        self.client.force_login(self.data[code]['users'][role])

    def assert_no_adnu(self, response):
        self.assertNotIn('ADNU_PRIVATE_', response.content.decode())

    def test_student_management_requires_role_and_scopes_both_list_and_delete(self):
        listing = reverse('superadmin:manage_students')
        foreign = self.data['ADNU']['users']['student']
        for role in ('student', 'faculty', 'depthead'):
            self.login(role)
            self.assertEqual(self.client.get(listing).status_code, 403)
            self.assertEqual(self.client.post(reverse('superadmin:remove_student_superadmin', args=[foreign.pk])).status_code, 403)
        self.login('superadmin')
        response = self.client.get(listing)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'UNC_PRIVATE_student')
        self.assert_no_adnu(response)
        self.assertEqual(self.client.post(reverse('superadmin:remove_student_superadmin', args=[foreign.pk])).status_code, 404)
        self.assertTrue(User.objects.filter(pk=foreign.pk).exists())
        own = self.data['UNC']['users']['student']
        self.assertEqual(self.client.post(reverse('superadmin:remove_student_superadmin', args=[own.pk])).status_code, 200)
        self.assertFalse(User.objects.filter(pk=own.pk).exists())

    def test_superadmin_pages_and_guessed_management_ids(self):
        self.login('superadmin')
        for route in ('superadmin_dashboard','manage_colleges','manage_admins','manage_faculty','manage_students'):
            with self.subTest(route=route):
                response = self.client.get(reverse('superadmin:' + route))
                self.assertEqual(response.status_code, 200)
                self.assert_no_adnu(response)
        adnu_college = College.objects.get(school=self.adnu, code='CCS')
        for route, pk in [('edit_college',adnu_college.pk),('delete_college',adnu_college.pk),
                          ('edit_depthead',self.data['ADNU']['users']['depthead'].pk),
                          ('remove_faculty_superadmin',self.data['ADNU']['users']['faculty'].pk)]:
            with self.subTest(route=route), patch('apps.superadmin.views.send_faculty_removed_email') as email:
                self.assertEqual(self.client.post(reverse('superadmin:' + route, args=[pk]), {}).status_code, 404)
                email.assert_not_called()

    @patch('apps.students.views.refresh_faculty_status')
    def test_student_directory_schedule_booking_walkins_and_subscriptions(self, refresh):
        self.login('student')
        for route in ('home','dashboard','api_faculty_statuses','consultation_requests','api_consultation_requests','active_announcements'):
            response = self.client.get(reverse('students:' + route))
            self.assertEqual(response.status_code, 200)
            self.assert_no_adnu(response)
        foreign = self.data['ADNU']['faculty']
        for route in ('view_schedule','api_schedule_events','api_walk_in_status'):
            self.assertEqual(self.client.get(reverse('students:' + route), {'faculty_id': foreign.pk}).status_code, 404)
        response = self.client.get(reverse('students:view_schedule'), {'faculty': self.data['ADNU']['users']['faculty'].username})
        self.assert_no_adnu(response)
        for method in ('get','post','delete'):
            self.assertEqual(getattr(self.client, method)(reverse('students:api_faculty_status_subscription', args=[foreign.pk])).status_code, 404)
        payload = {'faculty_id':foreign.pk,'date':timezone.localdate().isoformat(),'start_time':'11:00','end_time':'12:00','agenda':'general_concern'}
        for route in ('api_consultation_requests','api_join_walk_in_queue'):
            self.assertEqual(self.client.post(reverse('students:' + route), json.dumps(payload), content_type='application/json').status_code, 404)
        self.assertTrue(all(call.args[0].user.school_id == self.unc.pk for call in refresh.call_args_list))

    @patch('apps.students.views.delete_consultation_event')
    def test_student_cannot_cancel_or_delete_guessed_foreign_consultation(self, google):
        self.login('student')
        pk = self.data['ADNU']['consultation'].pk
        self.assertEqual(self.client.delete(reverse('students:api_delete_consultation', args=[pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse('students:api_request_consultation_cancellation', args=[pk])).status_code, 404)
        google.assert_not_called()
        self.assertEqual(ConsultationRequest.objects.get(pk=pk).status, 'approved')

    def test_faculty_cannot_read_or_mutate_foreign_events_consultations_or_queues(self):
        self.login('faculty')
        foreign = self.data['ADNU']
        for route, pk in [('api_schedule_event_detail',foreign['event'].pk),
                          ('api_consultation',foreign['consultation'].pk),('api_walk_in_detail',foreign['queue'].pk)]:
            url = reverse('faculty:' + route, args=[pk])
            for method in ('get','post','delete'):
                with self.subTest(route=route, method=method):
                    response = self.client.get(url) if method == 'get' else getattr(self.client,method)(url, data='{}', content_type='application/json')
                    self.assertEqual(response.status_code,404)
        response = self.client.post(reverse('faculty:api_schedule_events_bulk_delete'),
            json.dumps({'event_ids':[foreign['event'].pk]}), content_type='application/json')
        self.assertEqual(response.status_code,404)
        for route in ('dashboard','booking_management','schedule','profile','api_faculty_walk_ins','api_schedule_events','calendar_status'):
            response = self.client.get(reverse('faculty:' + route))
            self.assertEqual(response.status_code,200)
            self.assert_no_adnu(response)

    def test_college_head_pages_apis_and_guessed_schedule_ids(self):
        self.login('depthead')
        for route in ('admin_dashboard','admin_dashboard_legacy','admin_faculty','student_behavior','student_behavior_legacy',
                      'faculty_monitoring','faculty_monitoring_legacy','faculty_monitoring_data','college_settings','college_settings_legacy',
                      'peak_analytics','peak_analytics_legacy','faculty_trends','faculty_trends_legacy','closure_status',
                      'hourly_availability','shared_windows_api','ai_insights_api'):
            with self.subTest(route=route):
                response = self.client.get(reverse('depthead:' + route))
                self.assertEqual(response.status_code,200)
                self.assert_no_adnu(response)
        foreign = self.data['ADNU']
        for route, pk, method in [('remove_faculty',foreign['users']['faculty'].pk,'post'),
                                 ('upload_faculty_schedule',foreign['faculty'].pk,'post'),
                                 ('view_faculty_schedule_preview',foreign['faculty'].pk,'get'),
                                 ('delete_faculty_schedule',foreign['faculty'].pk,'post')]:
            self.assertEqual(getattr(self.client,method)(reverse('depthead:' + route,args=[pk])).status_code,404)

    def test_all_three_chatbots_stay_in_the_callers_school(self):
        for role, route, questions in [('depthead','depthead:analytics_browser_api',ANALYTICS_QUESTIONS),
                                       ('student','students:availability_browser_api',STUDENT_QUESTIONS),
                                       ('faculty','faculty:consultation_browser_api',FACULTY_QUESTIONS)]:
            self.login(role)
            for metric in questions:
                with self.subTest(role=role,metric=metric):
                    response = self.client.get(reverse(route),{'metric':metric,'school':self.adnu.pk,'college':'CCS'})
                    self.assertEqual(response.status_code,200)
                    self.assert_no_adnu(response)

    def test_analytics_services_require_explicit_school_and_reject_context_switch(self):
        self.assertIsNone(current_school())
        with self.assertRaises(PermissionDenied):
            get_college_analytics('CCS')
        for school in (self.adnu,self.unc):
            rows = list(get_base_consultation_queryset('CCS',school=school))
            self.assertEqual([row.pk for row in rows],[self.data[school.code]['consultation'].pk])
            data = get_college_analytics('CCS',school=school)
            self.assertEqual(data['consultations']['total_records'],1)
        with school_scope(self.unc), self.assertRaises(PermissionDenied):
            get_college_analytics('CCS',school=self.adnu)

    @patch('apps.depthead.services.ai_insights.genai.Client')
    def test_ai_cache_fresh_and_stale_fallback_cannot_cross_schools(self, client):
        for school in (self.adnu,self.unc):
            result = generate_ai_insights({'scope':{'college_code':'CCS'}},school=school)
            self.assertEqual(result['summary'],school.code + '_PRIVATE_AI')
        client.assert_not_called()
        self.data['UNC']['insight'].refresh_after = timezone.now() - timedelta(seconds=1)
        self.data['UNC']['insight'].save(update_fields=['refresh_after'])
        with override_settings(GEMINI_API_KEY=''):
            result = generate_ai_insights({'scope':{'college_code':'CCS'}},school=self.unc)
        self.assertTrue(result['stale'])
        self.assertEqual(result['summary'],'UNC_PRIVATE_AI')
        self.assertEqual(get_stored_ai_insights('CCS',school=self.adnu)['summary'],'ADNU_PRIVATE_AI')

    @override_settings(GEMINI_API_KEY='test-only')
    @patch('apps.depthead.services.ai_insights.genai.Client')
    def test_ai_refresh_writes_only_selected_school_and_missing_cache_does_not_fallback(self, client):
        self.data['UNC']['insight'].college_code='ccs'
        self.data['UNC']['insight'].save(update_fields=['college_code'])
        client.return_value.models.generate_content.return_value=SimpleNamespace(parsed={
            'summary':'UNC GENERATED','key_insights':[],'concerns':[],'recommendations':[],
        })
        result=generate_ai_insights({'scope':{'college_code':'CCS'}},force_refresh=True,school=self.unc)
        self.assertEqual(result['summary'],'UNC GENERATED')
        self.assertEqual(CollegeAIInsight.objects.get(school=self.unc).insights['summary'],'UNC GENERATED')
        self.assertEqual(CollegeAIInsight.objects.get(school=self.adnu).insights['summary'],'ADNU_PRIVATE_AI')
        CollegeAIInsight.objects.get(school=self.unc).delete()
        with override_settings(GEMINI_API_KEY=''):
            result=generate_ai_insights({'scope':{'college_code':'CCS'}},school=self.unc)
        self.assertFalse(result['available'])

    def test_foreign_notification_ids_and_private_photos_are_not_accessible(self):
        self.login('student')
        foreign=self.data['ADNU']['notification']
        url=reverse('core:notifications_api')
        self.assert_no_adnu(self.client.get(url))
        response=self.client.post(url,json.dumps({'notification_id':foreign.pk}),content_type='application/json')
        self.assertEqual(response.json()['updated'],0)
        response=self.client.delete(url,json.dumps({'notification_id':foreign.pk}),content_type='application/json')
        self.assertEqual(response.json()['deleted'],0)
        foreign.refresh_from_db()
        self.assertFalse(foreign.is_read)
        self.assertEqual(self.client.get(reverse('core:profile_photo_image',args=[self.data['ADNU']['users']['student'].pk])).status_code,403)

    def test_only_system_admin_can_browse_across_schools_in_database_admin(self):
        self.login('superadmin')
        self.assertEqual(self.client.get('/admin/core/user/').status_code,403)
        self.client.force_login(self.operator)
        response=self.client.get('/admin/core/user/')
        self.assertEqual(response.status_code,200)
        self.assertContains(response,'ADNU_PRIVATE_student')
        self.assertContains(response,'UNC_PRIVATE_student')

    def test_invite_activation_inherits_school_and_failed_save_keeps_invite(self):
        for model,role in [(FacultyInvite,'faculty'),(DeptHeadInvite,'depthead')]:
            invite=model.objects.create(school=self.unc,email=role+'-activation@example.invalid',college='CCS',
                invited_by=self.data['UNC']['users']['depthead'] if role=='faculty' else self.data['UNC']['users']['superadmin'])
            request=RequestFactory().get('/accounts/google/login/callback/')
            request.session={}
            request._messages=FallbackStorage(request)
            login=SimpleNamespace(is_existing=False,user=User(username='activated-'+role,email=invite.email),
                account=SimpleNamespace(provider='google',extra_data={'email':invite.email}))
            adapter=FacSyncSocialAdapter()
            adapter.pre_social_login(request,login)
            self.assertEqual(login.user.school_id,self.unc.pk)
            self.assertEqual(login.user.role,role)
            with patch.object(DefaultSocialAccountAdapter,'save_user',side_effect=RuntimeError('failed save')):
                with self.assertRaises(RuntimeError):
                    adapter.save_user(request,login)
            self.assertTrue(model.objects.filter(pk=invite.pk,used=False).exists())
            with patch.object(DefaultSocialAccountAdapter,'save_user',side_effect=lambda req,sl,form: (sl.user.save() or sl.user)):
                adapter.save_user(request,login)
            self.assertFalse(model.objects.filter(pk=invite.pk).exists())
            self.assertEqual(User.objects.get(username='activated-'+role).school_id,self.unc.pk)

    def test_suspended_school_blocks_existing_google_login_and_invite_activation(self):
        self.unc.is_active=False
        self.unc.save(actor=self.operator)
        request=RequestFactory().get('/accounts/google/login/callback/')
        request.session={}
        request._messages=FallbackStorage(request)
        user=self.data['UNC']['users']['faculty']
        login=SimpleNamespace(is_existing=True,user=user,
            account=SimpleNamespace(provider='google',extra_data={'email':user.email}))
        with self.assertRaises(ImmediateHttpResponse):
            FacSyncSocialAdapter().pre_social_login(request,login)
        invite=FacultyInvite.objects.create(school=self.unc,email='suspended@example.invalid',college='CCS')
        login=SimpleNamespace(is_existing=False,user=User(email=invite.email),
            account=SimpleNamespace(provider='google',extra_data={'email':invite.email}))
        with self.assertRaises(ImmediateHttpResponse):
            FacSyncSocialAdapter().pre_social_login(request,login)
        self.assertTrue(FacultyInvite.objects.filter(pk=invite.pk).exists())

    def test_invitation_identity_checks_do_not_reassign_other_schools_users(self):
        self.login('superadmin')
        foreign=self.data['ADNU']['users']['faculty']
        response=self.client.post(reverse('superadmin:invite_faculty_superadmin'),
            {'email':foreign.email,'college':'CCS'},HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(response.status_code,400)
        self.assert_no_adnu(response)
        self.assertFalse(FacultyInvite.objects.filter(email=foreign.email).exists())
        foreign.refresh_from_db()
        self.assertEqual(foreign.school_id,self.adnu.pk)

    def test_announcements_and_status_notifications_select_only_same_school_recipients(self):
        with school_scope(self.unc):
            created = notify_college_users('CCS','announcement','UNC only','UNC notification')
            self.assertTrue(created)
            self.assertEqual({obj.recipient.school_id for obj in created},{self.unc.pk})
            send_announcement_email_to_faculty(self.data['UNC']['announcement'])
        self.assertEqual([message.to for message in mail.outbox],[[self.data['UNC']['users']['faculty'].email]])
        with self.captureOnCommitCallbacks(execute=True):
            notifications = notify_faculty_status_subscribers(self.data['UNC']['faculty'],'busy')
        self.assertEqual({obj.recipient_id for obj in notifications},{self.data['UNC']['users']['student'].pk})
        self.assertEqual(mail.outbox[-1].to,[self.data['UNC']['users']['student'].email])

    def test_deferred_email_revalidates_school_equality_and_suspension(self):
        from apps.faculty.services.status_scheduler import claim_deliveries
        row = StatusEmailDelivery.objects.create(history=self.data['ADNU']['history'],
            recipient=self.data['ADNU']['users']['student'],email=self.data['UNC']['users']['student'].email,
            subject='fixture',body='fixture')
        # Simulate legacy-corrupt ownership without going through validated saves.
        StatusEmailDelivery._base_manager.filter(pk=row.pk).update(recipient_id=self.data['UNC']['users']['student'].pk)
        self.assertEqual(claim_deliveries(),[])
        row.refresh_from_db()
        self.assertEqual(row.state,'cancelled')
        self.unc.is_active=False
        self.unc.save(actor=self.operator)
        row2 = StatusEmailDelivery.objects.create(history=self.data['UNC']['history'],
            recipient=self.data['UNC']['users']['student'],email=self.data['UNC']['users']['student'].email,
            subject='fixture',body='fixture')
        self.assertEqual(claim_deliveries(),[])
        row2.refresh_from_db()
        self.assertEqual(row2.state,'cancelled')

    def test_public_dashboard_has_interim_login_and_school_scope(self):
        self.assertEqual(self.client.get(reverse('core:dashboard_public')).status_code,302)
        self.login('student')
        response=self.client.get(reverse('core:dashboard_public'))
        self.assertEqual(response.status_code,200)
        self.assert_no_adnu(response)
        self.assertIn('no-store',response['Cache-Control'])

    def test_missing_school_and_suspended_existing_sessions_are_blocked_for_each_role(self):
        unassigned=User.objects.create_user(username='unassigned',role='student')
        self.client.force_login(unassigned)
        self.assertEqual(self.client.get(reverse('students:dashboard')).status_code,403)
        self.unc.is_active=False
        self.unc.save(actor=self.operator)
        for role,route in [('student','students:dashboard'),('faculty','faculty:dashboard'),
                           ('depthead','depthead:admin_dashboard'),('superadmin','superadmin:manage_students')]:
            self.login(role)
            response=self.client.get(reverse(route))
            self.assertEqual(response.status_code,403)
            self.assertIn('suspended',response.content.decode())
        self.client.force_login(self.operator)
        self.assertEqual(self.client.get('/admin/').status_code,200)

    def test_forged_cross_school_relations_and_context_leakage_are_rejected(self):
        with self.assertRaises(ValidationError):
            ConsultationRequest.objects.create(request_id='mixed',user=self.data['UNC']['users']['student'],
                faculty=self.data['ADNU']['faculty'],date=timezone.localdate())
        with school_scope(self.unc):
            self.assertFalse(User.objects.filter(school=self.adnu).exists())
            with self.assertRaises(PermissionDenied):
                College.objects.create(school=self.adnu,code='FORGED',name='Forged')
            with self.assertRaises(PermissionDenied):
                User.objects.update(school=self.adnu)
            foreign=self.data['ADNU']['users']['student']
            foreign.school=self.unc
            with self.assertRaises(PermissionDenied):
                foreign.save(update_fields=['school'])
        self.assertIsNone(current_school())
        self.assertEqual(User.objects.filter(role='student').count(),2)
        with school_scope(ALL_SCHOOLS):
            self.assertEqual(User.objects.filter(role='student').count(),2)

    def test_invites_and_new_colleges_inherit_sender_school_and_ignore_forged_school(self):
        self.login('superadmin')
        response=self.client.post(reverse('superadmin:invite_depthead'),{'email':'new-head@example.invalid',
            'college':'CCS','title':'dean','school':self.adnu.pk})
        self.assertEqual(response.status_code,200)
        invite=DeptHeadInvite.objects.get(email='new-head@example.invalid')
        self.assertEqual(invite.school_id,self.unc.pk)
        self.assertEqual(invite.title,'dean')
        self.client.post(reverse('superadmin:create_college'),{'name':'UNC New College','description':'','school':self.adnu.pk})
        self.assertEqual(College.objects.get(name='UNC New College').school_id,self.unc.pk)
        self.login('depthead')
        self.client.post(reverse('depthead:invite_faculty'),{'email':'new-faculty@example.invalid','school':self.adnu.pk})
        self.assertEqual(FacultyInvite.objects.get(email='new-faculty@example.invalid').school_id,self.unc.pk)

    def test_profile_colleges_and_admin_role_edit_cannot_be_forged(self):
        other=College.objects.create(school=self.adnu,code='ADNUONLY',name='ADNU_PRIVATE_OTHER')
        self.login('student')
        response=self.client.get(reverse('core:student_profile_setup'))
        self.assert_no_adnu(response)
        response=self.client.post(reverse('core:student_profile_setup'),{'student_id':'123','college':other.code,'year_level':'2'})
        self.assertEqual(response.status_code,200)
        self.assertFalse(response.context['form'].is_valid())
        self.login('superadmin')
        head=self.data['UNC']['users']['depthead']
        response=self.client.post(reverse('superadmin:edit_depthead',args=[head.pk]),
            {'role':'systemadmin','college':'CCS','title':'dean','account_status':'active'})
        self.assertEqual(response.status_code,400)
        head.refresh_from_db()
        self.assertEqual(head.role,'depthead')
