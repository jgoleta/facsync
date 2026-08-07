from django.test import TestCase
from django.urls import reverse


class DeptheadViewTests(TestCase):
    def test_admin_dashboard_renders(self):
        response = self.client.get(reverse('depthead:admin_dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'depthead/adminDashboard.html')

    def test_admin_faculty_renders(self):
        response = self.client.get(reverse('depthead:admin_faculty'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'depthead/adminFaculty.html')

    def test_student_behavior_renders(self):
        response = self.client.get(reverse('depthead:student_behavior'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'depthead/studentBehavior.html')

    def test_faculty_monitoring_renders(self):
        response = self.client.get(reverse('depthead:faculty_monitoring'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'depthead/facultyMonitoring.html')

    def test_department_settings_renders(self):
        response = self.client.get(reverse('depthead:department_settings'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'depthead/departmentSettings.html')

    def test_peak_analytics_renders(self):
        response = self.client.get(reverse('depthead:peak_analytics'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'depthead/peakAnalytics.html')

    def test_faculty_trends_renders(self):
        response = self.client.get(reverse('depthead:faculty_trends'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'depthead/facultyTrends.html')
