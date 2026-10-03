from datetime import date, datetime, time, timedelta, timezone as dt_timezone
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.core.chat_presentation import date_label, duration, hour_range
from apps.core.department_updates import department_update_answer
from apps.core.models import CollegeAnnouncement, OfficeClosure, User
from apps.depthead.services.analytics_browser import analytics_browser_answer
from apps.depthead.services.analytics_display import schedule_availability_ai_summary, most_available_days_recommendation
from apps.depthead.services.schedule_availability import get_schedule_availability
from apps.faculty.models import ConsultationRequest, FacultyProfile, ScheduleEvent
from apps.faculty.services.consultation_browser import QUESTIONS, consultation_browser_answer
from apps.students.availability_browser import availability_answer


@override_settings(TIME_ZONE='Asia/Manila', GOOGLE_CALENDAR_TIME_ZONE='Asia/Manila')
class ConversationalHelperTests(TestCase):
    def setUp(self):
        clock = patch('django.utils.timezone.now', return_value=datetime(2026, 10, 3, 4, tzinfo=dt_timezone.utc))
        clock.start()
        self.addCleanup(clock.stop)
        self.student = User.objects.create(username='student', role='student', college='CCS')
        self.head = User.objects.create(username='head', role='depthead', college='CCS')
        self.faculty = self.make_faculty('John', 'CCS')
        self.other = self.make_faculty('Mary', 'CCS')
        self.external = self.make_faculty('PRIVATE', 'CBA')

    def make_faculty(self, name, college):
        user = User.objects.create(username=name, first_name=name, last_name='Doe', role='faculty', college=college)
        return FacultyProfile.objects.create(faculty_id=name, user=user, college_id=college, current_status='available')

    def request(self, profile, key, **extra):
        values = dict(request_id=key, faculty=profile, user=self.student, date=date(2026, 10, 3),
                      start_time=time(13, 30), end_time=time(14), status='completed', agenda='grade_consultation')
        values.update(extra)
        return ConsultationRequest.objects.create(**values)

    def test_readable_dates_durations_and_hour_buckets(self):
        self.assertEqual(date_label(date(2026, 10, 3)), 'October 3, 2026')
        self.assertEqual(duration(120), '2 hours')
        self.assertEqual(duration(61), '1 hour 1 minute')
        self.assertEqual(duration(0), '0 minutes')
        self.assertEqual(hour_range(0), '12 AM–12:59 AM')
        self.assertEqual(hour_range(12), '12 PM–12:59 PM')

    def test_available_now_is_dated_and_keeps_recorded_status_scope(self):
        self.other.current_status = 'virtual_only'
        self.other.save()
        result = availability_answer('available_now', 'CCS')
        self.assertIn('right now, October 3, 2026:', result['period'])
        self.assertEqual(result['lines'], ['John Doe'])
        self.assertEqual(result['note'], 'These are based on their latest recorded status. Check with the faculty member before visiting.')
        self.assertEqual(result['source_url'], reverse('students:dashboard'))
        self.assertEqual(result['source_label'], 'View faculty directory')

    def test_local_date_follows_manila_midnight(self):
        with patch('django.utils.timezone.now', return_value=datetime(2026, 10, 2, 16, 1, tzinfo=dt_timezone.utc)):
            self.assertIn('October 3, 2026', availability_answer('available_now', 'CCS')['period'])

    def test_student_empty_and_closure_are_paragraphs(self):
        FacultyProfile.objects.filter(college_id='CCS').update(current_status='busy')
        result = availability_answer('available_now', 'CCS')
        self.assertEqual(result['presentation'], 'paragraphs')
        self.assertIn('No faculty', result['lines'][0])
        OfficeClosure.objects.create(college='CCS', is_closed=True)
        result = availability_answer('available_now', 'CCS')
        self.assertIn('closed', result['lines'][0])
        self.assertNotIn('John', str(result))

    def test_faculty_peaks_and_topics_only_include_own_records(self):
        self.request(self.faculty, 'own')
        for index, faculty in enumerate([self.other, self.other, self.external]):
            self.request(faculty, f'other-{index}')
        result = consultation_browser_answer('peak_hour', self.faculty)
        self.assertEqual(result['lines'], ['1 PM–1:59 PM — 1 completed consultation'])
        self.assertIn('October 1, 2026 to October 3, 2026', result['period'])
        self.assertEqual(result['source_url'], reverse('faculty:dashboard') + '#consultation-requests')
        topics = consultation_browser_answer('consultation_topics', self.faculty)
        self.assertIn('May 1, 2026 to October 3, 2026', topics['period'])
        self.assertIn('1 request (100.00%)', str(topics['lines']))
        self.assertIn('0 requests (0.00%)', str(topics['lines']))

    def test_faculty_empty_messages_are_question_specific(self):
        messages = []
        for metric in ['peak_hour', 'peak_day', 'consultation_topics', 'peak_request_period', 'student_frequency']:
            result = consultation_browser_answer(metric, self.faculty)
            self.assertEqual(result['presentation'], 'paragraphs')
            self.assertNotIn('No data for', str(result))
            messages.append(result['lines'][0])
        self.assertEqual(len(set(messages)), 5)

    def test_submission_month_uses_submission_not_scheduled_date_and_shows_ties(self):
        for month in [8, 9]:
            record = self.request(self.faculty, f'month-{month}', date=date(2027, 1, 1))
            ConsultationRequest.objects.filter(pk=record.pk).update(requested_at=datetime(2026, month, 12, tzinfo=dt_timezone.utc))
        result = consultation_browser_answer('peak_request_period', self.faculty)
        self.assertEqual(result['lines'], ['August 2026 — 1 request', 'September 2026 — 1 request'])
        self.assertIn('submission date', result['note'])

    def test_college_peak_ties_and_scoped_counts(self):
        self.request(self.faculty, 'one', start_time=time(13, 30))
        self.request(self.other, 'two', start_time=time(14, 15))
        self.request(self.external, 'external', start_time=time(15))
        result = analytics_browser_answer('peak_hour', 'CCS')
        self.assertEqual(result['lines'], ['1 PM–1:59 PM — 1 completed consultation', '2 PM–2:59 PM — 1 completed consultation'])
        self.assertEqual(result['source_label'], 'View peak analytics')

    def test_announcements_keep_messages_and_role_college_expiry_filters(self):
        for college, audience, message, active in [('CCS', 'students', 'student notice', True),
                ('CCS', 'faculty', 'faculty notice', True), ('CCS', 'both', '<script>alert(1)</script>\nOriginal message', True),
                ('CBA', 'both', 'PRIVATE', True), ('CCS', 'both', 'EXPIRED', False)]:
            CollegeAnnouncement.objects.create(college=college, audience=audience, message=message, posted_by=self.head,
                                              expiry=timezone.now() + timedelta(days=1 if active else -1))
        for role, expected in [('student', 2), ('faculty', 2), ('depthead', 3)]:
            result = department_update_answer('active_announcements', 'CCS', role, '/dashboard/')
            self.assertEqual(len(result['announcements']), expected)
            self.assertNotIn('PRIVATE', str(result))
            self.assertNotIn('EXPIRED', str(result))
            if role == 'student':
                self.assertNotIn('faculty notice', str(result))
            if role == 'faculty':
                self.assertNotIn('student notice', str(result))
            self.assertEqual(result['announcements'][0]['message'], '<script>alert(1)</script>\nOriginal message')
            self.assertEqual(len(result['announcements'][0]['details']), 3)
            self.assertIn('October 4, 2026', result['announcements'][0]['details'][2])

    def test_open_closure_hides_old_details_and_missing_record_is_honest(self):
        result = department_update_answer('college_closure', 'CCS', 'student', '/')
        self.assertEqual(result['lines'], ['No college closure is currently recorded.'])
        OfficeClosure.objects.create(college='CCS', is_closed=False, reason='OLD REASON', closure_start=date(2025, 1, 1))
        result = department_update_answer('college_closure', 'CCS', 'student', '/')
        self.assertNotIn('OLD REASON', str(result))
        self.assertNotIn('2025', str(result))
        self.assertIn('marked as open', result['lines'][0])

    def test_closed_dates_do_not_override_saved_flag(self):
        OfficeClosure.objects.create(college='CCS', is_closed=True, reason='Maintenance', closure_end=date(2025, 1, 1))
        result = department_update_answer('college_closure', 'CCS', 'depthead', '/')
        self.assertIn('closed', result['period'])
        self.assertIn('Maintenance', str(result['lines']))
        self.assertIn('January 1, 2025', str(result['lines']))
        self.assertIn('do not automatically change', result['note'])

    def test_admin_zero_and_missing_values_stay_distinct(self):
        from apps.depthead.services.analytics import get_faculty_trends
        data = get_faculty_trends('CCS')
        data['items'][0]['completion_rate_percent'] = 0
        data['items'][1]['completion_rate_percent'] = None
        with patch('apps.depthead.services.analytics_browser.analytics.get_faculty_trends', return_value=data):
            result = analytics_browser_answer('completion_rates', 'CCS')
        self.assertIn('0%', result['lines'][0])
        self.assertIn('No scheduled requests', result['lines'][1])

    def test_faculty_api_rejects_role_guessing_and_ignores_other_faculty_id(self):
        self.request(self.faculty, 'own')
        self.request(self.other, 'not-own')
        self.client.force_login(self.faculty.user)
        url = reverse('faculty:consultation_browser_api')
        result = self.client.get(url, {'metric': 'peak_hour', 'faculty_id': self.other.pk, 'college': 'CBA'})
        self.assertEqual(result.status_code, 200)
        self.assertEqual(len(result.json()['lines']), 1)
        self.assertIn('1 completed consultation', result.json()['lines'][0])
        self.assertEqual(self.client.get(url, {'metric': 'completion_rates'}).status_code, 400)
        self.assertEqual(self.client.post(url).status_code, 405)
        for user in [self.student, self.head]:
            self.client.force_login(user)
            self.assertEqual(self.client.get(url, {'metric': 'peak_hour'}).status_code, 403)

    def test_faculty_no_profile_or_missing_college_and_anonymous_access(self):
        url = reverse('faculty:consultation_browser_api')
        self.assertEqual(self.client.get(url, {'metric': 'peak_hour'}).status_code, 302)
        missing = User.objects.create(username='no-profile', role='faculty')
        self.client.force_login(missing)
        self.assertEqual(self.client.get(url, {'metric': 'peak_hour'}).status_code, 400)
        self.client.force_login(self.faculty.user)
        self.faculty.college_id = ''
        self.faculty.save()
        self.assertEqual(self.client.get(url, {'metric': 'peak_hour'}).status_code, 400)

    def test_faculty_questions_read_only_and_dashboard_link_target_exists(self):
        self.client.force_login(self.faculty.user)
        with patch('apps.faculty.views.refresh_faculty_status') as refresh:
            for metric in QUESTIONS:
                result = self.client.get(reverse('faculty:consultation_browser_api'), {'metric': metric})
                self.assertEqual(result.status_code, 200)
                self.assertIn('no-store', result['Cache-Control'])
            refresh.assert_not_called()
            response = self.client.get(reverse('faculty:dashboard'))
        self.assertContains(response, 'id="consultation-requests"', count=1)

    def test_two_hour_count_shared_by_student_admin_chart_ai_and_recommendation(self):
        # Exclude unrelated profiles from this threshold scenario.
        self.other.user.account_status = 'deactivated'
        self.other.user.save()
        ScheduleEvent.objects.create(faculty=self.faculty, title='Class', date=date(2026, 10, 3), start_time=time(8), end_time=time(16))
        data = get_schedule_availability('CCS', today=date(2026, 10, 3))
        saturday = data['rows'][5]
        self.assertEqual(saturday['available_count'], 0)
        self.assertEqual(saturday['open_minutes'], 60)
        self.assertEqual(saturday['winners'], ['John Doe'])  # Total-time ranking unchanged.
        student = availability_answer('best_day', 'CCS')
        self.assertNotIn('Saturday', str(student['lines']))
        self.assertIn('two consecutive hours', student['note'])
        admin = analytics_browser_answer('daily_availability', 'CCS')
        self.assertIn('0 of 1 faculty (0%)', admin['lines'][5])
        ai = schedule_availability_ai_summary(data)
        self.assertEqual(ai['minimum_free_minutes'], 120)
        self.assertEqual(ai['daily'][5]['available_count'], 0)
        self.assertIn('without recorded schedules', ai['interpretation'])
        self.assertNotIn('Saturday', most_available_days_recommendation(data)['description'])
        self.client.force_login(self.head)
        self.assertContains(self.client.get(reverse('depthead:faculty_trends')), 'At least two consecutive hours')
