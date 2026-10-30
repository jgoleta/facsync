from django.contrib.auth import get_user_model
from apps.core.tests.school_case import SchoolTestCase as TestCase
from django.urls import reverse


class LogoutTests(TestCase):
    def test_logout_clears_authenticated_session(self):
        user = get_user_model().objects.create_user(
            username='logout-test',
            password='test-password',
        )
        self.client.force_login(user)

        response = self.client.get(reverse('account_logout'))

        self.assertRedirects(response, reverse('core:landing'))
        self.assertNotIn('_auth_user_id', self.client.session)
