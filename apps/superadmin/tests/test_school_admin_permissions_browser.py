import os
from unittest import skipUnless
from unittest.mock import patch

from django.conf import settings
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import override_settings
from django.urls import reverse

from apps.core.models import School, User


@skipUnless(os.environ.get('DEPARTMENT_BROWSER_TESTS') == '1', 'Opt-in browser checks')
@override_settings(SESSION_ENGINE='django.contrib.sessions.backends.signed_cookies')
class SchoolAdminPermissionsBrowserTests(StaticLiveServerTestCase):
    def test_invite_defaults_edit_prefill_and_limited_navigation(self):
        operator = User.objects.create_user(username='permissions-ui-operator', role='systemadmin')
        school = School(code='PERMISSIONSUI', name='Permissions UI school')
        school.save(actor=operator)
        owner = User.objects.create_user(username='permissions-ui-owner', role='superadmin', school=school)
        limited = User.objects.create_user(username='permissions-ui-limited', role='superadmin', school=school,
            school_admin_full_access=False)
        self.client.force_login(limited)
        limited_cookie = self.client.cookies[settings.SESSION_COOKIE_NAME].value
        self.client.force_login(owner)
        owner_cookie = self.client.cookies[settings.SESSION_COOKIE_NAME].value
        from playwright.sync_api import expect, sync_playwright
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                context = browser.new_context(viewport={'width': 1360, 'height': 900})
                context.route('**/*', lambda route: route.continue_() if route.request.url.startswith(self.live_server_url) else route.abort())
                context.add_cookies([{'name': settings.SESSION_COOKIE_NAME, 'value': owner_cookie, 'url': self.live_server_url}])
                page = context.new_page()
                errors = []
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.goto(self.live_server_url + reverse('superadmin:manage_superadmins'))
                trigger = page.get_by_role('button', name='Invite School Admin', exact=True)
                trigger.click()
                invite = page.locator('#superAdminInviteModal')
                expect(invite.locator('input[name=permissions]:checked')).to_have_count(2)
                expect(invite.locator('input[value=colleges]')).to_be_checked()
                expect(invite.locator('input[value=departments]')).to_be_checked()
                invite.locator('input[name=email]').fill('permissions-ui@example.invalid')
                invite.locator('input[value=faculty]').check()
                with patch('apps.superadmin.superadmin_views.send_superadmin_invite_email', return_value=True):
                    invite.get_by_role('button', name='Send Invite', exact=True).click()
                    expect(page.get_by_role('cell', name='permissions-ui@example.invalid', exact=True)).to_be_visible()
                row = page.get_by_role('row').filter(has=page.get_by_role('cell', name='permissions-ui@example.invalid', exact=True))
                row.get_by_role('button', name='Edit permissions', exact=True).click()
                edit = page.locator('#schoolAdminPermissionsModal')
                expect(edit.locator('input[name=permissions]:checked')).to_have_count(3)
                expect(edit.locator('input[value=faculty]')).to_be_checked()
                page.keyboard.press('Escape')
                expect(edit).not_to_be_visible()
                expect(row.get_by_role('button', name='Edit permissions', exact=True)).to_be_focused()
                context.add_cookies([{'name': settings.SESSION_COOKIE_NAME, 'value': limited_cookie, 'url': self.live_server_url}])
                page.goto(self.live_server_url + reverse('superadmin:superadmin_dashboard'))
                expect(page.locator('.sidebar-nav a')).to_have_count(3)
                expect(page.get_by_role('link', name='School Overview', exact=True)).to_be_visible()
                self.assertEqual(page.goto(self.live_server_url + reverse('superadmin:manage_superadmins')).status, 403)
                self.assertEqual(errors, [])
            finally:
                browser.close()
