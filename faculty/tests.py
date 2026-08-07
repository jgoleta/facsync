from django.test import TestCase
from django.urls import reverse


class FacultyViewTests(TestCase):
    def test_dashboard_page_renders(self):
        response = self.client.get(reverse('faculty:dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'faculty/dashboardFaculty.html')

    def test_booking_page_renders(self):
        response = self.client.get(reverse('faculty:booking_management'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'faculty/bookingManagement.html')

    def test_profile_page_renders(self):
        response = self.client.get(reverse('faculty:profile'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'faculty/profile.html')

    def test_schedule_page_renders(self):
        response = self.client.get(reverse('faculty:schedule'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'faculty/scheduleFaculty.html')
