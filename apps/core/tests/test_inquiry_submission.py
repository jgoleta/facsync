from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from apps.core.models import SchoolInquiry


class InquirySubmissionTests(TestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        self.url = reverse('core:school_inquiry')
        self.data = dict(representative_name='Representative', email='rep@school.example.org',
            position='Director', school_name='Example School', declaration='on')
        self.receipt = patch('apps.core.services.send_school_inquiry_receipt', return_value=True).start()
        self.notification = patch('apps.core.services.send_school_inquiry_notification', return_value=True).start()
        self.addCleanup(patch.stopall)

    def test_submission_and_refresh(self):
        response = self.client.post(self.url, self.data, follow=True)
        self.assertContains(response, 'Submission reference:')
        self.assertEqual(SchoolInquiry.objects.count(), 1)
        self.client.get(response.redirect_chain[-1][0])
        self.assertEqual(SchoolInquiry.objects.count(), 1)
        self.receipt.assert_called_once()
        self.notification.assert_called_once()

    def test_duplicate_keeps_same_public_message_and_does_not_send_again(self):
        first = self.client.post(self.url, self.data, follow=True)
        second = self.client.post(self.url, self.data, follow=True)
        self.assertEqual(first.context['description'], second.context['description'])
        self.assertEqual(SchoolInquiry.objects.count(), 1)
        self.receipt.assert_called_once()
        self.assertNotEqual(first.context['submission_reference'], second.context['submission_reference'])

    def test_email_failure_preserves_inquiry_and_records_failure(self):
        self.receipt.side_effect = RuntimeError('Provider unavailable')
        response = self.client.post(self.url, self.data, follow=True)
        self.assertEqual(response.status_code, 200)
        item = SchoolInquiry.objects.get()
        self.assertTrue(item.events.filter(action='receipt_email_failed').exists())
        self.assertTrue(item.events.filter(action='notification_email_accepted').exists())
        self.assertContains(response, 'Email updates may be delayed')

    def test_rate_limit_is_explicit(self):
        for _ in range(5):
            self.client.post(self.url, self.data)
        response = self.client.post(self.url, self.data)
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response['Retry-After'], '3600')
        self.assertEqual(SchoolInquiry.objects.count(), 1)

    def test_authorization_is_required(self):
        self.data.pop('declaration')
        self.client.post(self.url, self.data)
        self.assertFalse(SchoolInquiry.objects.exists())
        self.receipt.assert_not_called()
