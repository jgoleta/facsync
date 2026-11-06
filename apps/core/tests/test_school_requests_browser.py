import os
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest import skipUnless

from django.conf import settings
from django.contrib.sessions.backends.signed_cookies import SessionStore
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import override_settings
from django.urls import reverse

from apps.core.models import School, SchoolRegistrationRequest, SuperAdminInvite, User
from apps.core.school_requests import IDENTITY_KEY
from apps.systemadmin.registration_services import submit_request


@skipUnless(os.environ.get('DEPARTMENT_BROWSER_TESTS') == '1', 'Opt-in browser checks')
@override_settings(SESSION_ENGINE='django.contrib.sessions.backends.signed_cookies')
class SchoolRequestBrowserTests(StaticLiveServerTestCase):
    def setUp(self):
        super().setUp()
        operator=User.objects.create_user(username='school-request-ui-reviewer',email='reviewer@example.invalid',role='systemadmin')
        self.client.force_login(operator)
        reviewer_cookie=self.client.cookies[settings.SESSION_COOKIE_NAME].value
        self.identity={'email':'representative@browser-request.edu.ph','subject':'browser-subject',
            'domain':'browser-request.edu.ph','name':'Browser Representative','issued_at':time.time()}
        session=SessionStore()
        session[IDENTITY_KEY]=self.identity
        session.save()
        self.applicant_cookie=session.session_key
        self.data={'school_name':'Browser Request School','school_code':'BR_REQUEST',
            'representative_name':'Browser Representative','position':'School representative',
            'educational_levels':['college'],'contact_email':'principal@browser-request.edu.ph','website':'https://browser-request.edu.ph'}
        from playwright.sync_api import sync_playwright
        self.playwright=sync_playwright().start()
        self.browser=self.playwright.chromium.launch()
        self.context=self.browser.new_context(viewport={'width':1360,'height':900})
        self.context.route('**/*',lambda route:route.continue_() if route.request.url.startswith(self.live_server_url) else route.abort())
        self.context.add_cookies([{'name':settings.SESSION_COOKIE_NAME,'value':reviewer_cookie,'url':self.live_server_url}])
        self.page=self.context.new_page()
        self.errors=[]
        self.page.on('pageerror',lambda error:self.errors.append(str(error)))

    def tearDown(self):
        try:
            self.browser.close()
            self.playwright.stop()
        finally:
            super().tearDown()

    def database(self,callback):
        with ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(callback).result()

    def visit(self,name):
        self.page.goto(self.live_server_url+reverse(name))

    def screenshot(self,name):
        folder=Path(settings.BASE_DIR)/'.staging-backups/school-registration'
        folder.mkdir(parents=True,exist_ok=True)
        self.page.screenshot(path=str(folder/name),full_page=True)

    def test_applicant_form_submission_pending_status_and_mobile(self):
        from playwright.sync_api import expect
        self.context.add_cookies([{'name':settings.SESSION_COOKIE_NAME,'value':self.applicant_cookie,'url':self.live_server_url}])
        before=self.database(lambda:(User.objects.count(),School.objects.count()))
        self.visit('core:school_registration')
        for name in ('school_name','school_code','position','contact_email','website'):
            self.page.locator(f'[name={name}]').fill(self.data[name])
        self.screenshot('applicant-form.png')
        self.page.get_by_role('button',name='Submit Registration Request').click()
        expect(self.page.get_by_role('heading',name='Pending review',exact=True)).to_be_visible()
        self.assertEqual(self.database(lambda:(User.objects.count(),School.objects.count())),before)
        self.assertEqual(self.database(lambda:SchoolRegistrationRequest.objects.count()),1)
        self.page.set_viewport_size({'width':390,'height':844})
        self.assertLessEqual(self.page.evaluate('document.documentElement.scrollWidth'),391)
        self.screenshot('applicant-status-mobile.png')
        self.assertFalse(self.errors)

    def test_reviewer_modal_errors_approval_and_readonly_history(self):
        from playwright.sync_api import expect
        item_id=self.database(lambda:str(submit_request(self.identity,self.data)[0].pk))
        self.visit('systemadmin:school_requests')
        expect(self.page.locator('.brand')).to_contain_text('FacSync Administration')
        expect(self.page.locator('.sidebar-nav a').first).to_have_text('System Overview')
        expect(self.page.locator('.sidebar-nav a')).to_have_count(4)
        expect(self.page.locator('.system-request-card #request-status')).to_have_count(0)
        expect(self.page.get_by_role('button', name='Filter', exact=True)).to_have_count(0)
        self.screenshot('requests-directory.png')
        self.page.get_by_role('link',name='Review',exact=True).click()
        modal=self.page.locator('#system-form-modal')
        expect(modal).to_be_visible()
        self.screenshot('review-modal.png')
        modal.get_by_role('button',name='Save Decision').click()
        expect(modal.locator('.errorlist')).to_contain_text('Complete this field')
        modal.locator('[name=verification_notes]').fill('Official contact independently confirmed authority.')
        modal.get_by_role('button',name='Save Decision').click()
        expect(modal).not_to_be_visible()
        self.assertEqual(self.database(lambda:SchoolRegistrationRequest.objects.get(pk=item_id).status),'approved')
        self.assertEqual(self.database(lambda:SuperAdminInvite.objects.filter(email=self.identity['email']).count()),1)
        self.page.locator('#request-status').select_option('approved')
        expect(self.page).to_have_url(self.live_server_url+reverse('systemadmin:school_requests')+'?status=approved')
        self.page.get_by_role('link',name='View',exact=True).click()
        expect(modal).to_contain_text('Official contact independently confirmed authority.')
        expect(modal.get_by_role('button',name='Save Decision')).to_have_count(0)
        self.assertFalse(self.errors)

    def test_signed_in_page_buttons_and_only_actionable_messages(self):
        from django.contrib.messages import constants
        from django.contrib.messages.storage.base import Message
        from django.contrib.messages.storage.cookie import CookieStorage
        from playwright.sync_api import expect
        encoded = CookieStorage(None)._encode([
            Message(constants.SUCCESS, 'Successfully signed in as reviewer.'),
            Message(constants.ERROR, 'Verify a different institutional email to continue.'),
        ])
        self.context.add_cookies([{'name': 'messages', 'value': encoded, 'url': self.live_server_url}])
        self.visit('core:school_registration')
        expect(self.page.get_by_text('Successfully signed in as reviewer.')).to_have_count(0)
        expect(self.page.get_by_role('alert')).to_have_text('Verify a different institutional email to continue.')
        expect(self.page.get_by_role('link', name='Return to your dashboard')).to_have_attribute('href', reverse('core:post_login_redirect'))
        expect(self.page.get_by_role('link', name='Back to home')).to_be_visible()
        expect(self.page.get_by_role('link', name='Student registration')).to_have_count(0)
        self.screenshot('signed-in-registration.png')
        self.page.set_viewport_size({'width':390,'height':844})
        self.assertLessEqual(self.page.evaluate('document.documentElement.scrollWidth'),391)
        self.assertFalse(self.errors)

    def test_unverified_public_page_has_only_google_entry_and_submit_lock(self):
        from playwright.sync_api import expect
        self.context.clear_cookies()
        self.visit('core:school_registration')
        expect(self.page.locator('[name=school_name]')).to_have_count(0)
        button=self.page.locator('form[data-school-request-submit] button[type=submit]')
        expect(button).to_be_visible()
        form=self.page.locator('form[data-school-request-submit]')
        form.evaluate('(form)=>form.dispatchEvent(new Event("submit",{bubbles:true,cancelable:true}))')
        expect(button).to_be_disabled()
        self.assertFalse(form.evaluate('(form)=>form.dispatchEvent(new Event("submit",{bubbles:true,cancelable:true}))'))
        self.page.evaluate('window.dispatchEvent(new Event("pageshow"))')
        expect(button).to_be_enabled()
        self.page.set_viewport_size({'width':390,'height':844})
        self.assertLessEqual(self.page.evaluate('document.documentElement.scrollWidth'),391)
        self.assertFalse(self.errors)
