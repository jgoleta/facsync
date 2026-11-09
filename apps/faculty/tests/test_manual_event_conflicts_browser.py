import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest import skipUnless
from unittest.mock import patch

from django.conf import settings
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import override_settings
from django.urls import reverse

from apps.core.models import School, User
from apps.faculty.models import FacultyProfile, GoogleCalendarConnection, ScheduleEvent


@skipUnless(os.environ.get('DEPARTMENT_BROWSER_TESTS') == '1', 'Opt-in browser checks')
@override_settings(SESSION_ENGINE='django.contrib.sessions.backends.signed_cookies')
class ManualEventConflictBrowserTests(StaticLiveServerTestCase):
    def setUp(self):
        super().setUp()
        operator = User.objects.create_user(username='overlap-browser-operator',role='systemadmin')
        school = School(code='OVERLAP_BROWSER', name='Overlap browser school'); school.save(actor=operator)
        user = User.objects.create_user(username='overlap-browser',role='faculty',school=school,profile_completed=True)
        FacultyProfile.objects.create(user=user,faculty_id='overlap-browser')
        GoogleCalendarConnection.objects.create(user=user,google_user_id='synthetic',access_token='synthetic')
        self.client.force_login(user)
        self.enterContext(patch('apps.faculty.views.refresh_faculty_status'))
        self.enterContext(patch('apps.faculty.views.sync_google_calendar'))
        self.google = self.enterContext(patch('apps.faculty.services.manual_event_conflicts.list_google_events',return_value=[{
            'id':'existing-google', 'summary':'Advisement <img src=x onerror=alert(1)>',
            'start':{'dateTime':'2026-11-10T09:00:00+08:00'}, 'end':{'dateTime':'2026-11-10T10:00:00+08:00'},
        }]))
        self.create = self.enterContext(patch('apps.faculty.views.create_google_event',return_value={'id':'new-google'}))
        from playwright.sync_api import sync_playwright
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch()
        self.context = self.browser.new_context(viewport={'width':1360,'height':1000})
        self.context.route('**/*',lambda route:route.continue_() if route.request.url.startswith(self.live_server_url) else route.abort())
        self.context.add_cookies([{'name':settings.SESSION_COOKIE_NAME,'value':self.client.cookies[settings.SESSION_COOKIE_NAME].value,'url':self.live_server_url}])
        self.page = self.context.new_page()
        self.errors = []
        self.page.on('pageerror',lambda error:self.errors.append(str(error)))

    def tearDown(self):
        try:
            self.browser.close(); self.playwright.stop()
        finally:
            super().tearDown()

    def count(self):
        with ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(ScheduleEvent.objects.count).result()

    def begin(self):
        self.page.goto(self.live_server_url + reverse('faculty:schedule'))
        self.page.wait_for_function('document.querySelector("#calendar-sync-status").textContent.includes("Schedule loaded") || document.querySelector("#calendar-sync-status").textContent.includes("synced")')
        self.page.locator('#add-event-btn').click()
        self.page.locator('#eventTitle').fill('My new schedule')
        self.page.locator('#eventStartTime').fill('2026-11-10T09:00')
        self.page.locator('#eventEndTime').fill('2026-11-10T10:00')

    def submit(self):
        self.page.locator('#addEventForm button[type=submit]').click()
        self.page.locator('#googleCalendarConfirmYes').click()

    def test_warning_preserves_form_cancel_and_confirm_with_safe_text_mobile(self):
        from playwright.sync_api import expect
        self.begin(); self.submit()
        dialog = self.page.locator('.schedule-overlap-dialog')
        expect(dialog).to_be_visible()
        expect(dialog).to_contain_text('Advisement <img src=x onerror=alert(1)>')
        expect(dialog.locator('img')).to_have_count(0)
        expect(dialog).to_contain_text('9:00')
        expect(dialog.get_by_role('button',name='Go back')).to_be_focused()
        self.assertEqual(self.count(),0); self.create.assert_not_called()
        self.page.locator('#addEventForm').evaluate('(form)=>form.dispatchEvent(new Event("submit", {bubbles:true,cancelable:true}))')
        self.assertEqual(self.google.call_count,1)
        dialog.get_by_role('button',name='Go back').click()
        expect(dialog).to_have_count(0)
        expect(self.page.locator('#eventTitle')).to_have_value('My new schedule')
        self.assertEqual(self.count(),0)
        self.submit(); expect(dialog).to_be_visible()
        folder=Path(settings.BASE_DIR)/'.staging-backups/manual-event-overlaps'; folder.mkdir(parents=True,exist_ok=True)
        self.page.screenshot(path=str(folder/'desktop.png'),full_page=True)
        self.page.set_viewport_size({'width':390,'height':844})
        self.assertLessEqual(self.page.evaluate('document.documentElement.scrollWidth'),391)
        self.page.screenshot(path=str(folder/'mobile.png'),full_page=True)
        dialog.get_by_role('button',name='Save anyway').click()
        expect(self.page.locator('#addEventModal')).to_have_class('modal-overlay hidden')
        self.assertEqual(self.count(),1); self.create.assert_called_once()
        self.assertFalse(self.errors)

    def test_escape_cancels_without_saving(self):
        from playwright.sync_api import expect
        self.begin(); self.submit()
        expect(self.page.locator('.schedule-overlap-dialog')).to_be_visible()
        self.page.keyboard.press('Escape')
        expect(self.page.locator('.schedule-overlap-dialog')).to_have_count(0)
        self.assertEqual(self.count(),0); self.create.assert_not_called()
        expect(self.page.locator('#eventTitle')).to_have_value('My new schedule')
        self.assertFalse(self.errors)
