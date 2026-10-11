from datetime import date, datetime, time, timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.test import TestCase, override_settings
from django.urls import reverse

from apps.core.models import User
from apps.faculty.models import FacultyProfile, ScheduleEvent, ConsultationRequest
from apps.faculty.services.google_calendar import refresh_faculty_status
from apps.depthead.services.shared_windows import find_shared_windows, planning_week


@override_settings(GOOGLE_CALENDAR_TIME_ZONE='Asia/Manila')
class SharedWindowTests(TestCase):
    monday = date(2026, 10, 12)
    now = datetime(2026, 10, 12, 7, tzinfo=ZoneInfo('Asia/Manila'))

    def faculty(self, name, college='CCS', active=True):
        user = User.objects.create(username=name, role='faculty', college=college,
                                   account_status='active' if active else 'deactivated')
        return FacultyProfile.objects.create(faculty_id=name, user=user, college_id=college)

    def event(self, faculty, **kwargs):
        values = dict(title='Private commitment', date=self.monday,
                      start_time=time(7), end_time=time(8))
        values.update(kwargs)
        return ScheduleEvent.objects.create(faculty=faculty, **values)

    def find(self, duration=120, day=None, now=None):
        return find_shared_windows('ccs', day or self.monday, duration, now=now or self.now)

    def test_everyone_free_together_and_all_tied_starts_preserved(self):
        for name in ('Alpha', 'Beta'):
            self.event(self.faculty(name))
        with self.assertNumQueries(3):
            result = self.find()
        self.assertEqual(result['best_count'], 2)
        self.assertEqual(result['message'], '')
        self.assertEqual(len(result['windows']), 1)
        window = result['windows'][0]
        self.assertEqual(window['start'].time(), time(8))
        self.assertEqual(window['latest_start'].time(), time(15))
        self.assertEqual(window['latest_end'].time(), time(17))
        self.assertEqual((window['free_count'], window['conflict_count'], window['unknown_count']), (2, 0, 0))

    def test_no_shared_slot_and_zero_free_distinguished(self):
        alpha = self.faculty('Alpha')
        beta = self.faculty('Beta')
        self.event(alpha, start_time=time(8), end_time=time(12))
        self.event(beta, start_time=time(12), end_time=time(17))
        result = self.find()
        self.assertEqual(result['best_count'], 1)
        self.assertIn('No window has all faculty', result['message'])
        self.assertEqual(len(result['windows']), 2)
        self.assertEqual(result['windows'][0]['free'][0]['id'], 'Beta')
        self.assertEqual(result['windows'][1]['free'][0]['id'], 'Alpha')
        ScheduleEvent.objects.all().update(start_time=None, end_time=None)
        result = self.find()
        self.assertEqual(result['best_count'], 0)
        self.assertIn('No window has any faculty', result['message'])
        self.assertEqual(result['windows'][0]['conflict_count'], 2)

    def test_unknown_day_data_and_college_scope(self):
        self.event(self.faculty('Known'))
        self.faculty('No schedule')
        self.event(self.faculty('Other day'), date=self.monday + timedelta(days=1))
        self.event(self.faculty('Other college', 'CBA'))
        self.event(self.faculty('Inactive', active=False))
        result = self.find()
        self.assertEqual(result['faculty_count'], 3)
        self.assertEqual(result['best_count'], 1)
        self.assertEqual(result['windows'][0]['unknown_count'], 2)

    def test_equal_counts_with_different_members_are_not_combined(self):
        alpha, beta = self.faculty('Alpha'), self.faculty('Beta')
        self.event(alpha, start_time=time(8), end_time=time(9))
        self.event(beta, start_time=time(9), end_time=time(17))
        windows = self.find(duration=60)['windows']
        self.assertEqual(len(windows), 2)
        self.assertEqual(windows[0]['start'].time(), time(8))
        self.assertEqual(windows[0]['latest_start'].time(), time(8))
        self.assertEqual(windows[1]['start'].time(), time(9))
        self.assertNotEqual(windows[0]['free'], windows[1]['free'])

    def test_query_count_stays_fixed_for_thirty_faculty_and_is_read_only(self):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        for index in range(30):
            self.event(self.faculty(f'Faculty {index}'))
        with CaptureQueriesContext(connection) as queries:
            result = self.find()
        self.assertEqual(len(queries), 3)
        self.assertEqual(result['best_count'], 30)
        for query in queries:
            self.assertTrue(query['sql'].lstrip().upper().startswith('SELECT'))

    def test_consultations_conflict_without_establishing_full_day_knowledge(self):
        faculty = self.faculty('Consultant')
        ConsultationRequest.objects.create(request_id='approved', faculty=faculty, user=faculty.user,
                                           date=self.monday, start_time=time(8), end_time=time(10),
                                           status='cancellation_requested')
        result = self.find()
        self.assertEqual(result['best_count'], 0)
        self.assertEqual(result['windows'][0]['conflict_count'], 1)
        self.assertEqual(result['windows'][-1]['unknown_count'], 1)
        self.event(faculty)
        ConsultationRequest.objects.create(request_id='pending', faculty=faculty, user=faculty.user,
                                           date=self.monday, start_time=time(10), end_time=time(17),
                                           status='pending')
        result = self.find()
        self.assertEqual(result['best_count'], 1)
        self.assertEqual(result['windows'][0]['start'].time(), time(10))

    def test_recurrence_exclusions_boundaries_and_overnight(self):
        faculty = self.faculty('Recurring')
        self.event(faculty, date=None, day_of_week='monday', start_month=10, end_month=2,
                   recurrence_start_date=self.monday, recurrence_end_date=self.monday,
                   start_time=time(7), end_time=time(8))
        overnight = self.event(faculty, date=self.monday - timedelta(days=1),
                               start_time=time(23), end_time=time(10))
        self.assertEqual(self.find()['windows'][0]['start'].time(), time(10))
        overnight.delete()
        recurring = ScheduleEvent.objects.get(faculty=faculty)
        recurring.recurrence_excluded_dates = [self.monday.isoformat()]
        recurring.save()
        self.assertIn('All faculty have unknown', self.find()['message'])

    def test_stale_events_and_manual_status_do_not_make_missing_day_free(self):
        faculty = self.faculty('Stale')
        self.event(faculty, google_event_id='external', sync_state='out_of_sync')
        faculty.manual_status_override = True
        faculty.manual_status = 'available'
        faculty.save()
        result = self.find()
        self.assertEqual(result['windows'][0]['unknown_count'], 1)
        self.assertEqual(result['best_count'], 0)

    def test_duration_weekday_and_elapsed_time_validation(self):
        self.event(self.faculty('Known'))
        for day in (self.monday - timedelta(days=1), self.monday + timedelta(days=5),
                    self.monday + timedelta(days=7)):
            with self.subTest(day=day), self.assertRaises(ValueError):
                self.find(day=day)
        with self.assertRaises(ValueError):
            self.find(duration=0)
        now = self.now.replace(hour=10, minute=1)
        self.assertEqual(self.find(now=now)['windows'][0]['start'].time(), time(10, 15))
        self.assertIn('No remaining', self.find(duration=540, now=now)['message'])
        self.assertEqual(self.find(duration=540)['windows'][0]['end'].time(), time(17))

    @patch('apps.depthead.services.shared_windows.timezone.now')
    def test_form_week_restriction_results_and_access(self, clock):
        clock.return_value = self.now
        self.event(self.faculty('Known'))
        head = User.objects.create(username='head', role='depthead', college='CCS')
        self.client.force_login(head)
        url = reverse('depthead:faculty_trends')
        response = self.client.get(url, {'date': self.monday.isoformat(), 'duration': '120', 'college': 'CBA'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Find best times')
        self.assertContains(response, '1 free')
        self.assertContains(response, '0 unknown')
        self.assertNotContains(response, 'College-wide availability by day')
        self.assertNotContains(response, 'Private commitment')
        self.assertContains(response, 'Most available faculty per day')
        for params in ({'date': '2026-10-17', 'duration': '120'},
                       {'date': 'bad', 'duration': '60'},
                       {'date': '2026-10-12', 'duration': '999'}):
            response = self.client.get(url, params)
            self.assertIsNone(response.context['planner_result'])
            self.assertTrue(response.context['planner_form'].errors)
        head.role = 'student'
        head.save()
        self.assertEqual(self.client.get(url).status_code, 403)

    @patch('apps.depthead.services.shared_windows.timezone.now')
    def test_weekend_form_can_search_current_week_and_local_week(self, clock):
        clock.return_value = self.now + timedelta(days=5)
        head = User.objects.create(username='head', role='depthead', college='CCS')
        self.client.force_login(head)
        response = self.client.get(reverse('depthead:faculty_trends'))
        self.assertNotContains(response, "planning period has ended")
        self.assertContains(response, '<button type="submit">Find best times</button>')
        self.assertFalse(response.context['planner_form'].fields['date'].disabled)
        self.assertEqual(response.context['planner_result']['date'], self.monday + timedelta(days=4))
        self.event(self.faculty('Weekend review'))
        response = self.client.get(reverse('depthead:faculty_trends'),
                                   {'date': self.monday.isoformat(), 'duration': '120'})
        self.assertContains(response, '1 free')
        self.assertFalse(response.context['planner_form'].errors)
        utc_sunday = datetime(2026, 10, 11, 17, tzinfo=ZoneInfo('UTC'))
        self.assertEqual(planning_week(utc_sunday)['week_start'], self.monday)

    @patch('apps.depthead.services.shared_windows.timezone.now')
    def test_result_summary_bar_day_selector_and_visible_faculty(self, clock):
        clock.return_value = self.now
        self.event(self.faculty('Known'))
        self.faculty('Unknown')
        head = User.objects.create(username='presentation-head', role='depthead', college='CCS')
        self.client.force_login(head)
        response = self.client.get(reverse('depthead:faculty_trends'))
        self.assertContains(response, '1 of 2 faculty free based on recorded schedules')
        self.assertContains(response, 'shared-window-bar')
        self.assertNotContains(response, 'Unknown means no schedule data exists for that day.</p>')
        self.assertContains(response, 'How is this calculated?')
        self.assertNotContains(response, '<summary>How is this calculated?</summary>')
        self.assertNotContains(response, 'View faculty')
        self.assertContains(response, 'shared-window-faculty')
        self.assertContains(response, 'Mon, Oct 12')
        self.assertContains(response, 'Fri, Oct 16')
        self.assertContains(response, '<select name="date"')
        self.assertNotContains(response, 'type="date"')
        clock.return_value = self.now + timedelta(days=2)
        response = self.client.get(reverse('depthead:faculty_trends'))
        options = response.context['planner_form'].fields['date'].widget
        self.assertTrue(options.create_option('date', '2026-10-12', 'Monday', False, 0)['attrs']['disabled'])
        self.assertNotIn('disabled', options.create_option('date', '2026-10-14', 'Wednesday', True, 2)['attrs'])

    @patch('apps.depthead.services.shared_windows.timezone.now')
    def test_json_endpoint_scoped_read_only_and_validation(self, clock):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        clock.return_value = self.now
        self.event(self.faculty('Local'))
        self.event(self.faculty('PRIVATE OTHER COLLEGE', 'CBA'))
        head = User.objects.create(username='endpoint-head', role='depthead', college='CCS')
        self.client.force_login(head)
        url = reverse('depthead:shared_windows_api')
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get(url, {'date': '2026-10-12', 'duration': '120', 'college': 'CBA'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(queries), 5)  # Session + user + three planner SELECTs.
        self.assertTrue(all(q['sql'].lstrip().upper().startswith('SELECT') for q in queries))
        self.assertIn('no-store', response['Cache-Control'])
        html = response.json()['html']
        self.assertIn('1 of 1 faculty free based on recorded schedules', html)
        self.assertNotIn('PRIVATE OTHER COLLEGE', html)
        self.assertNotIn('Private commitment', html)
        self.assertNotIn('<!doctype', html)
        invalid = self.client.get(url, {'date': '2026-10-17', 'duration': '120'})
        self.assertEqual(invalid.status_code, 400)
        self.assertIn('errorlist', invalid.json()['html'])
        self.assertEqual(self.client.post(url).status_code, 405)
        head.college = ''
        head.save()
        self.assertEqual(self.client.get(url).status_code, 400)
        head.role = 'student'
        head.save()
        self.assertEqual(self.client.get(url).status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.get(url).status_code, 302)

    @patch('apps.depthead.services.shared_windows.timezone.now')
    @patch('apps.depthead.views.find_shared_windows')
    def test_window_buttons_preserve_all_windows_and_summary(self, planner, clock):
        clock.return_value = self.now
        head = User.objects.create(username='more-head', role='depthead', college='CCS')
        self.client.force_login(head)
        windows = []
        for hour in range(8, 12):
            start = datetime.combine(self.monday, time(hour))
            windows.append(dict(start=start, end=start + timedelta(hours=2), latest_start=start,
                                free_count=1, conflict_count=0, unknown_count=0,
                                free=[{'id': 'faculty', 'name': 'Faculty'}], conflict=[], unknown=[]))
        planner.return_value = dict(date=self.monday, duration_minutes=120, faculty_count=1,
                                    windows=windows, message='')
        response = self.client.get(reverse('depthead:shared_windows_api'))
        html = response.json()['html']
        self.assertNotIn('Show more', html)
        self.assertEqual(html.count('aria-controls="shared-window-panel-'), 4)
        self.assertEqual(html.count('aria-pressed="true"'), 1)
        self.assertEqual(sum(f'aria-labelledby="shared-window-button-{i}" hidden>' in html for i in range(1, 5)), 3)
        self.assertNotIn('120-minute event', html)
        self.assertNotIn('Any 15-minute start', html)
        self.assertEqual(html.count('class="shared-window-result"'), 4)
        self.assertEqual(html.count('1 of 1 faculty free based on recorded schedules'), 4)

    @patch('apps.faculty.services.google_calendar.notify_faculty_status_subscribers')
    @patch('apps.faculty.services.google_calendar.timezone.now')
    def test_status_refresh_reuses_recurrence_and_overnight_rules(self, clock, notify):
        clock.return_value = self.now.replace(hour=9)
        faculty = self.faculty('Status')
        self.event(faculty, date=None, day_of_week='monday', start_month=10, end_month=12,
                   start_time=time(8), end_time=time(17),
                   recurrence_excluded_dates=[self.monday.isoformat()])
        self.assertEqual(refresh_faculty_status(faculty), 'not_set')
        self.event(faculty, date=self.monday - timedelta(days=1), start_time=time(23), end_time=time(10))
        self.assertEqual(refresh_faculty_status(faculty), 'busy')
        clock.return_value = self.now.replace(hour=10)
        self.assertEqual(refresh_faculty_status(faculty), 'not_set')

    @patch('apps.faculty.services.google_calendar.notify_faculty_status_subscribers')
    @patch('apps.faculty.services.google_calendar.timezone.now')
    def test_status_priority_manual_override_and_consultation_commitments(self, clock, notify):
        clock.return_value = self.now.replace(hour=9)
        faculty = self.faculty('Priority')
        ConsultationRequest.objects.create(request_id='commitment', faculty=faculty, user=faculty.user,
                                           date=self.monday, start_time=time(8), end_time=time(10),
                                           status='approved')
        self.assertEqual(refresh_faculty_status(faculty), 'busy')
        virtual = self.event(faculty, start_time=time(8), end_time=time(10), event_type='virtual')
        self.assertEqual(refresh_faculty_status(faculty), 'virtual_only')
        leave = self.event(faculty, start_time=None, end_time=None, event_type='on-leave')
        self.assertEqual(refresh_faculty_status(faculty), 'on_leave')
        faculty.manual_status_override = True
        faculty.manual_status = 'available'
        faculty.save()
        self.assertEqual(refresh_faculty_status(faculty), 'available')
        # The planner still respects commitments even with a manual Available.
        self.assertEqual(self.find()['best_count'], 0)
        leave.delete()
        virtual.delete()
