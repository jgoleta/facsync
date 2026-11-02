from types import SimpleNamespace
from unittest.mock import patch

from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.core.models import School, SuperAdminInvite, User
from apps.core.services import send_superadmin_deactivated_email, send_superadmin_invite_email
from apps.systemadmin.views import _deliver_deactivation, _deliver_invite


@override_settings(SITE_URL='https://facsync.example/')
class SuperAdminEmailTests(TestCase):
    def setUp(self):
        self.operator = User.objects.create_user(username='email-system-admin', role='systemadmin')
        self.school = School(name='<School & Co>', code='MAIL')
        self.school.save(actor=self.operator)
        self.admin = User.objects.create_user(username='email-super-admin', first_name='<Admin>',
            email='admin@example.invalid', role='superadmin', school=self.school)
        self.replacement = User.objects.create_user(username='email-replacement',
            email='replacement@example.invalid', role='superadmin', school=self.school)
        self.client.force_login(self.operator)
        self.invite_url = reverse('systemadmin:invite_add')
        self.status_url = reverse('systemadmin:superadmin_status', args=[self.admin.pk])

    def invite(self):
        return self.client.post(self.invite_url, {'email': 'invited@example.invalid', 'school': self.school.pk})

    def change_status(self, action):
        return self.client.post(self.status_url, {'action': action})

    def test_invite_has_one_styled_login_button_and_correct_school_recipient(self):
        self.assertEqual(self.invite().status_code, 302)
        invite = SuperAdminInvite.objects.get()
        self.assertEqual(invite.school, self.school)
        self.assertEqual(invite.invited_by, self.operator)
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, ['invited@example.invalid'])
        self.assertIn('Sign in with Google', message.body)
        self.assertIn('https://facsync.example/login/', message.body)
        html = message.alternatives[0].content
        self.assertIn('&lt;School &amp; Co&gt;', html)
        self.assertNotIn('<School', html)
        self.assertEqual(html.count('<a '), 1)
        self.assertIn('href="https://facsync.example/login/"', html)
        self.assertIn('Activate Account', html)

    def test_invite_failure_preserves_saved_invitation(self):
        for result in (RuntimeError('private-secret'), 0):
            with self.subTest(result=type(result).__name__):
                SuperAdminInvite.objects.all().delete()
                options = {'side_effect': result} if isinstance(result, Exception) else {'return_value': result}
                with patch('apps.core.services._send_html_email', **options), self.assertLogs(
                    'apps.systemadmin.views', level='WARNING',
                ) as logs:
                    self.assertEqual(self.invite().status_code, 302)
                self.assertTrue(SuperAdminInvite.objects.filter(email='invited@example.invalid').exists())
                self.assertNotIn('private-secret', str(logs.output))
                self.assertNotIn('invited@example.invalid', str(logs.output))

    def test_resend_uses_same_email_without_new_invitation(self):
        self.invite()
        invite = SuperAdminInvite.objects.get()
        self.assertEqual(self.client.post(reverse('systemadmin:invite_resend', args=[invite.pk])).status_code, 302)
        self.assertEqual(SuperAdminInvite.objects.count(), 1)
        self.assertEqual(len(mail.outbox), 2)
        self.assertEqual(mail.outbox[-1].to, ['invited@example.invalid'])

    def test_deactivation_only_emails_on_active_to_deactivated_transition(self):
        self.assertEqual(self.change_status('deactivate').status_code, 302)
        self.admin.refresh_from_db()
        self.assertFalse(self.admin.is_active)
        self.assertEqual(self.admin.account_status, 'deactivated')
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, [self.admin.email])
        html = message.alternatives[0].content
        self.assertIn('&lt;Admin&gt;', html)
        self.assertIn('&lt;School &amp; Co&gt;', html)
        self.assertIn('System Admin', html)
        self.assertNotIn('<Admin>', html)
        self.change_status('deactivate')
        self.change_status('reactivate')
        self.assertEqual(len(mail.outbox), 1)
        self.change_status('deactivate')
        self.assertEqual(len(mail.outbox), 2)

    def test_deactivation_failure_preserves_status_change(self):
        with patch('apps.core.services._send_html_email', side_effect=RuntimeError('private-secret')), \
                self.assertLogs('apps.systemadmin.views', level='WARNING') as logs:
            self.assertEqual(self.change_status('deactivate').status_code, 302)
        self.admin.refresh_from_db()
        self.assertFalse(self.admin.is_active)
        self.assertEqual(self.admin.account_status, 'deactivated')
        self.assertNotIn('private-secret', str(logs.output))

    def test_last_active_superadmin_cannot_be_deactivated_or_emailed(self):
        self.replacement.is_active = False
        self.replacement.save(update_fields=['is_active'])
        self.change_status('deactivate')
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_active)
        self.assertEqual(self.admin.account_status, 'active')
        self.assertEqual(len(mail.outbox), 0)

    def test_missing_address_skips_both_services_and_view_helpers_silently(self):
        self.admin.email = '  '
        request = SimpleNamespace()
        with patch('apps.core.services._send_html_email') as sender, self.assertNoLogs(
            'apps.systemadmin.views', level='WARNING',
        ):
            self.assertFalse(send_superadmin_invite_email('', self.school))
            self.assertFalse(send_superadmin_deactivated_email(self.admin))
            _deliver_invite(request, SimpleNamespace(email=''))
            _deliver_deactivation(request, self.admin)
        sender.assert_not_called()

    def test_non_system_admin_roles_cannot_invite_resend_or_deactivate(self):
        self.invite()
        invite = SuperAdminInvite.objects.get()
        mail.outbox.clear()
        for role in ('student', 'faculty', 'depthead', 'superadmin'):
            user = User.objects.create_user(username=f'email-forbidden-{role}', role=role, school=self.school)
            self.client.force_login(user)
            for url in (self.invite_url, self.status_url,
                        reverse('systemadmin:invite_resend', args=[invite.pk]),
                        reverse('systemadmin:invite_status', args=[invite.pk])):
                with self.subTest(role=role, url=url):
                    self.assertEqual(self.client.post(url, {'action': 'deactivate',
                        'email': 'another@example.invalid', 'school': self.school.pk}).status_code, 403)
        self.assertEqual(SuperAdminInvite.objects.count(), 1)
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_active)
        self.assertEqual(len(mail.outbox), 0)

    def test_invitation_deactivation_and_reactivation_do_not_email(self):
        self.invite()
        invite = SuperAdminInvite.objects.get()
        mail.outbox.clear()
        url = reverse('systemadmin:invite_status', args=[invite.pk])
        for action in ('deactivate', 'reactivate'):
            self.assertEqual(self.client.post(url, {'action': action}).status_code, 302)
        self.assertEqual(len(mail.outbox), 0)

    def test_status_changes_require_post(self):
        self.assertEqual(self.client.get(self.status_url).status_code, 405)
        self.assertEqual(len(mail.outbox), 0)

    def test_used_invitation_cannot_be_resent(self):
        self.invite()
        invite = SuperAdminInvite.objects.get()
        invite.used = True
        invite.save(update_fields=['used'])
        mail.outbox.clear()
        self.assertEqual(self.client.post(reverse('systemadmin:invite_resend', args=[invite.pk])).status_code, 404)
        self.assertEqual(len(mail.outbox), 0)
