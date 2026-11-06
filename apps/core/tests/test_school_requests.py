import time
from unittest.mock import patch

from allauth.core.exceptions import ImmediateHttpResponse
from allauth.socialaccount.models import SocialAccount, SocialLogin
from django.contrib.auth.models import AnonymousUser
from django.contrib.messages.storage.fallback import FallbackStorage
from django.core import mail
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError
from django.test import Client, RequestFactory, TestCase, override_settings
from django.urls import reverse

from apps.core.adapters import FacSyncSocialAdapter
from apps.core.models import School, SchoolDomain, SchoolRegistrationRequest, SuperAdminInvite, User, OfficeAdminInvite
from apps.core.school_requests import IDENTITY_KEY, INTENT_KEY, applicant_identity
from apps.systemadmin.registration_services import review_request, submit_request


@override_settings(SITE_URL='https://facsync.example', EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class SchoolRequestTests(TestCase):
    def setUp(self):
        self.operator = User.objects.create_user(username='request-reviewer', email='reviewer@example.invalid', role='systemadmin')
        self.identity = {'email': 'representative@request-school.edu.ph', 'subject': 'google-request-subject',
                         'domain': 'request-school.edu.ph', 'name': 'School Representative', 'issued_at': time.time()}
        self.data = {'school_name': 'Request school', 'school_code': 'REQUEST', 'representative_name': 'School Representative',
            'position': 'School representative', 'educational_levels': ['college','jhs'],
            'contact_email': 'principal@request-school.edu.ph', 'website': 'https://request-school.edu.ph'}
        session = self.client.session
        session[IDENTITY_KEY] = self.identity
        session.save()
        self.public = reverse('core:school_registration')

    def submit(self):
        return submit_request(self.identity, self.data)[0]

    def reviewer(self):
        self.client.force_login(self.operator)

    def callback(self, email=None, verified=True, existing=None):
        request = RequestFactory().get('/accounts/google/login/callback/')
        from django.contrib.sessions.backends.signed_cookies import SessionStore
        request.session = SessionStore()
        request.session[INTENT_KEY] = time.time()
        request.user = AnonymousUser()
        request._messages = FallbackStorage(request)
        user = existing or User(username='request-new-user', email=email or self.identity['email'])
        login = SocialLogin(user=user, account=SocialAccount(provider='google', uid=self.identity['subject'],
            extra_data={'email': email or self.identity['email'], 'email_verified': verified, 'name': 'Representative'}))
        return request, login

    def test_verified_callback_creates_only_session_not_user_or_social_account(self):
        before = (User.objects.count(), SocialAccount.objects.count(), School.objects.count())
        request, login = self.callback()
        with self.assertRaises(ImmediateHttpResponse) as result:
            FacSyncSocialAdapter().pre_social_login(request, login)
        self.assertEqual(result.exception.response.url, self.public)
        self.assertEqual(applicant_identity(request)['email'], self.identity['email'])
        self.assertNotIn(INTENT_KEY, request.session)
        self.assertEqual((User.objects.count(), SocialAccount.objects.count(), School.objects.count()), before)

    def test_personal_unverified_expired_and_existing_identities_are_rejected(self):
        existing = User.objects.create_user(username='existing-request-student', email=self.identity['email'],
            school=School.objects.get(code='ADNU'), role='student')
        for values in ({'email':'personal@gmail.com'}, {'verified':False}, {'existing':existing}):
            request, login = self.callback(**values)
            with self.assertRaises(ImmediateHttpResponse):
                FacSyncSocialAdapter().pre_social_login(request, login)
            self.assertNotIn(IDENTITY_KEY, request.session)
        request, login = self.callback(email='new@request-school.edu.ph')
        request.session[INTENT_KEY] = time.time() - 901
        with self.assertRaises(ImmediateHttpResponse):
            FacSyncSocialAdapter().pre_social_login(request, login)
        self.assertIsNone(applicant_identity(request))

    def test_submission_creates_request_emails_but_no_school_user_or_invite(self):
        before = (School.objects.count(), User.objects.count(), SuperAdminInvite.objects.count())
        response = self.client.post(self.public, self.data)
        self.assertEqual(response.status_code, 302)
        item = SchoolRegistrationRequest.objects.get()
        self.assertEqual(item.domain, self.identity['domain'])
        self.assertEqual(item.applicant_email, self.identity['email'])
        self.assertEqual(item.status, 'pending')
        self.assertEqual((School.objects.count(), User.objects.count(), SuperAdminInvite.objects.count()), before)
        self.assertEqual(len(mail.outbox), 2)
        self.assertEqual(mail.outbox[0].to, [self.identity['email']])
        self.assertEqual(mail.outbox[1].to, [self.operator.email])

    def test_duplicate_submission_does_not_duplicate_request_or_emails(self):
        self.client.post(self.public, self.data)
        self.client.post(self.public, self.data)
        self.assertEqual(SchoolRegistrationRequest.objects.count(), 1)
        self.assertEqual(len(mail.outbox), 2)

    def test_pending_does_not_reserve_domain_for_another_representative(self):
        self.submit()
        other = {**self.identity, 'subject':'other-subject', 'email':'other@request-school.edu.ph'}
        second, created = submit_request(other, self.data)
        self.assertTrue(created)
        self.assertEqual(SchoolRegistrationRequest.objects.filter(domain=second.domain).count(), 2)

    def test_identity_and_domain_cannot_be_overridden_by_post_fields(self):
        data = {**self.data, 'applicant_email':'attacker@gmail.com', 'google_subject':'forged', 'domain':'another.edu.ph',
                'status':'approved', 'role':'systemadmin'}
        self.assertEqual(self.client.post(self.public, data).status_code, 302)
        item = SchoolRegistrationRequest.objects.get()
        self.assertEqual((item.applicant_email,item.google_subject,item.domain,item.status),
            (self.identity['email'],self.identity['subject'],self.identity['domain'],'pending'))

    def test_missing_proof_and_expired_session_cannot_submit(self):
        for client in (Client(), self.client):
            if client is self.client:
                session = client.session
                session[IDENTITY_KEY] = {**self.identity,'issued_at':time.time()-3601}
                session.save()
            self.assertEqual(client.post(self.public,self.data).status_code,302)
        self.assertFalse(SchoolRegistrationRequest.objects.exists())

    def test_validation_and_registered_domain_errors(self):
        for key, value in (('school_name',''),('school_code','bad code'),('contact_email','someone@gmail.com'),
                ('educational_levels',['unknown']),('website','not a URL')):
            with self.subTest(field=key):
                self.assertEqual(self.client.post(self.public,{**self.data,key:value}).status_code,400)
        SchoolDomain(school=School.objects.get(code='ADNU'),domain=self.identity['domain']).save(actor=self.operator)
        self.assertEqual(self.client.post(self.public,self.data).status_code,400)
        self.assertFalse(SchoolRegistrationRequest.objects.exists())

    def test_public_status_is_private_to_verified_subject_and_email(self):
        item=self.submit()
        self.assertContains(self.client.get(self.public),str(item.pk))
        other=Client()
        session=other.session
        session[IDENTITY_KEY]={**self.identity,'subject':'other-subject'}
        session.save()
        self.assertNotContains(other.get(self.public,{'id':str(item.pk),'email':item.applicant_email}),str(item.pk))
        self.assertIn('no-store',self.client.get(self.public)['Cache-Control'])

    def test_only_administration_can_list_review_and_approve(self):
        item=self.submit()
        for role in ('student','faculty','depthead','officeadmin','superadmin'):
            user=User.objects.create_user(username='request-'+role,role=role,school=School.objects.get(code='ADNU'))
            self.client.force_login(user)
            self.assertEqual(self.client.get(reverse('systemadmin:school_requests')).status_code,403)
            url=reverse('systemadmin:request_review',args=[item.pk])
            self.assertEqual(self.client.get(url).status_code,403)
            self.assertEqual(self.client.post(url,{'decision':'approve','verification_notes':'forged'}).status_code,403)
            with self.assertRaises(PermissionDenied):
                review_request(item.pk,actor=user,decision='approve',verification_notes='forged')

    def test_approval_creates_school_domain_invite_and_records_verification(self):
        item=self.submit()
        self.reviewer()
        users=User.objects.count()
        response=self.client.post(reverse('systemadmin:request_review',args=[item.pk]),
            {'decision':'approve','verification_notes':'Official website contact independently confirmed authority.'})
        self.assertEqual(response.status_code,302)
        item.refresh_from_db()
        self.assertEqual(item.status,'approved')
        self.assertEqual(item.approved_school.domains.get().domain,self.identity['domain'])
        self.assertEqual(item.approved_school.educational_levels,['college','jhs'])
        self.assertEqual(item.invitation.email,self.identity['email'])
        self.assertEqual(item.reviewed_by,self.operator)
        self.assertIsNotNone(item.reviewed_at)
        self.assertEqual(User.objects.count(),users)
        self.assertEqual(len(mail.outbox),1)
        self.assertIn('Activate Account',mail.outbox[0].alternatives[0].content)
        self.assertNotIn('independently confirmed',mail.outbox[0].body)

    def test_approved_representative_activates_through_existing_google_invite_flow(self):
        item=self.submit()
        saved,_=review_request(item.pk,actor=self.operator,decision='approve',verification_notes='Verified official contact')
        request,login=self.callback()
        request.session.pop(INTENT_KEY)
        adapter=FacSyncSocialAdapter()
        adapter.pre_social_login(request,login)
        self.assertEqual(login.user.role,'superadmin')
        self.assertEqual(login.user.school_id,saved.approved_school_id)
        user=adapter.save_user(request,login)
        self.assertEqual(user.role,'superadmin')
        self.assertTrue(user.profile_completed)
        saved.invitation.refresh_from_db()
        self.assertTrue(saved.invitation.used)

    def test_required_verification_and_rejection_reason(self):
        item=self.submit()
        self.reviewer()
        url=reverse('systemadmin:request_review',args=[item.pk])
        for decision in ('approve','reject'):
            response=self.client.post(url,{'decision':decision})
            self.assertEqual(response.status_code,200)
            self.assertContains(response,'Complete this field')
        item.refresh_from_db()
        self.assertEqual(item.status,'pending')

    def test_repeated_approval_does_not_duplicate_schools_invites_or_emails(self):
        item=self.submit()
        self.reviewer()
        url=reverse('systemadmin:request_review',args=[item.pk])
        data={'decision':'approve','verification_notes':'Verified independently'}
        self.client.post(url,data)
        before=(School.objects.count(),SuperAdminInvite.objects.count(),len(mail.outbox))
        self.client.post(url,data)
        self.assertEqual((School.objects.count(),SuperAdminInvite.objects.count(),len(mail.outbox)),before)

    def test_competing_request_cannot_claim_approved_domain_or_leave_partial_school(self):
        first=self.submit()
        second,_=submit_request({**self.identity,'subject':'second','email':'second@request-school.edu.ph'},self.data)
        review_request(first.pk,actor=self.operator,decision='approve',verification_notes='Verified')
        before=School.objects.count()
        with self.assertRaises(ValidationError):
            review_request(second.pk,actor=self.operator,decision='approve',verification_notes='Verified')
        self.assertEqual(School.objects.count(),before)
        second.refresh_from_db()
        self.assertEqual(second.status,'pending')

    def test_mid_approval_failure_rolls_back_school_domain_audit_and_request(self):
        item=self.submit()
        before=School.objects.count()
        with patch.object(SuperAdminInvite,'save',side_effect=IntegrityError('simulated conflict')):
            with self.assertRaises(IntegrityError):
                review_request(item.pk,actor=self.operator,decision='approve',verification_notes='Verified')
        self.assertEqual(School.objects.count(),before)
        self.assertFalse(SchoolDomain.objects.filter(domain=item.domain).exists())
        item.refresh_from_db()
        self.assertEqual(item.status,'pending')

    def test_failed_emails_do_not_undo_submission_or_approval(self):
        with (patch('apps.core.services.send_school_request_receipt',side_effect=RuntimeError('mail unavailable')),
              patch('apps.core.services.send_school_request_notification',side_effect=RuntimeError('mail unavailable'))):
            self.assertEqual(self.client.post(self.public,self.data).status_code,302)
        item=SchoolRegistrationRequest.objects.get()
        self.reviewer()
        with patch('apps.systemadmin.views.send_superadmin_invite_email',side_effect=RuntimeError('mail unavailable')):
            self.assertEqual(self.client.post(reverse('systemadmin:request_review',args=[item.pk]),
                {'decision':'approve','verification_notes':'Verified'}).status_code,302)
        item.refresh_from_db()
        self.assertEqual(item.status,'approved')
        self.assertIsNotNone(item.invitation_id)

    def test_rejection_exposes_reason_but_not_private_notes(self):
        item=self.submit()
        self.reviewer()
        response=self.client.post(reverse('systemadmin:request_review',args=[item.pk]),
            {'decision':'reject','verification_notes':'PRIVATE_INTERNAL_NOTE','decision_reason':'Please provide another official contact.'})
        self.assertEqual(response.status_code,302)
        self.client.logout()
        session=self.client.session
        session[IDENTITY_KEY]=self.identity
        session.save()
        response=self.client.get(self.public)
        self.assertContains(response,'Please provide another official contact.')
        self.assertNotContains(response,'PRIVATE_INTERNAL_NOTE')
        self.assertNotIn('PRIVATE_INTERNAL_NOTE',mail.outbox[0].body)
        self.assertFalse(SuperAdminInvite.objects.exists())

    def test_content_escaped_and_reset_does_not_expose_other_requests(self):
        item=submit_request(self.identity,{**self.data,'school_name':'<script>school</script>'})[0]
        self.assertNotContains(self.client.get(self.public),'<script>school</script>')
        self.assertContains(self.client.get(self.public),'&lt;script&gt;school&lt;/script&gt;')
        self.assertEqual(self.client.post(reverse('core:school_registration_reset')).status_code,302)
        self.assertNotContains(self.client.get(self.public),str(item.pk))

    def test_normal_login_and_student_signup_clear_stale_request_intent(self):
        for name in ('login','register','register_student'):
            session=self.client.session
            session[INTENT_KEY]=time.time()
            session.save()
            self.client.get(reverse('core:'+name))
            self.assertNotIn(INTENT_KEY,self.client.session)
