from datetime import date, datetime, time
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.test import TestCase, override_settings

from apps.core.models import Notification, School, User
from apps.core.school_scope import school_scope
from apps.faculty.models import FacultyProfile, ScheduleEvent, StatusHistory
from apps.faculty.services.google_calendar import refresh_faculty_status
from apps.students.models import FacultyStatusSubscription


@override_settings(GOOGLE_CALENDAR_TIME_ZONE='Asia/Manila', AUTOMATIC_STATUS_EMAIL_QUEUE_ENABLED=False)
class CalendarStatusMappingTests(TestCase):
    def setUp(self):
        self.school = School.objects.get(code='ADNU')
        self.user = User.objects.create_user(username='mapping-faculty', role='faculty', school=self.school)
        self.faculty = FacultyProfile.objects.create(user=self.user, faculty_id='mapping-faculty',
            college_id='CCS', current_status='busy', manual_status_override=False)

    def event(self, event_type, start=time(9), end=time(10), **extra):
        return ScheduleEvent.objects.create(faculty=self.faculty, title=event_type,
            event_type=event_type, date=date(2026, 11, 2), start_time=start, end_time=end, **extra)

    def status_at(self, hour, minute=0, second=0, **kwargs):
        now = datetime(2026, 11, 2, hour, minute, second, tzinfo=ZoneInfo('Asia/Manila'))
        with patch('apps.faculty.services.google_calendar.timezone.now', return_value=now), school_scope(self.school):
            return refresh_faculty_status(self.faculty, **kwargs)

    def test_unavailable_busy_unavailable_sequence_and_exact_boundaries(self):
        self.event('unavailable', time(9), time(9, 30))
        self.event('busy', time(9, 30), time(10))
        self.event('unavailable', time(10), time(10, 30))
        for stamp, expected in [((8, 59, 59), 'not_set'), ((9, 0, 0), 'unavailable'),
            ((9, 15, 0), 'unavailable'), ((9, 29, 59), 'unavailable'), ((9, 30, 0), 'busy'),
            ((9, 45, 0), 'busy'), ((9, 59, 59), 'busy'), ((10, 0, 0), 'unavailable'),
            ((10, 15, 0), 'unavailable'), ((10, 29, 59), 'unavailable'), ((10, 30, 0), 'not_set')]:
            with self.subTest(time=stamp):
                self.assertEqual(self.status_at(*stamp), expected)

    def test_google_linked_unavailable_record_retains_status(self):
        self.event('unavailable', google_event_id='synthetic-google-event', sync_state='synced', managed_by_facsync=True)
        raw_google_event = {'summary': 'Google copy', 'start': {'dateTime': '2026-11-02T09:00:00+08:00'},
                            'end': {'dateTime': '2026-11-02T10:00:00+08:00'}}
        self.assertEqual(self.status_at(9, 15, google_events=[raw_google_event]), 'unavailable')

    def test_overlap_priority_and_ties_are_deterministic(self):
        for types, expected in [(('busy', 'unavailable'), 'unavailable'),
            (('unavailable', 'busy'), 'unavailable'), (('virtual', 'unavailable'), 'unavailable'),
            (('unavailable', 'virtual'), 'unavailable'), (('unavailable', 'on-leave'), 'on_leave'),
            (('on-leave', 'unavailable'), 'on_leave'), (('unavailable', 'unavailable'), 'unavailable')]:
            with self.subTest(types=types):
                ScheduleEvent.objects.filter(faculty=self.faculty).delete()
                for event_type in types:
                    self.event(event_type)
                self.assertEqual(self.status_at(9, 15), expected)

    def test_existing_busy_on_leave_and_legacy_virtual_mappings_unchanged(self):
        for event_type, expected in [('busy', 'busy'), ('on-leave', 'on_leave'), ('virtual', 'virtual_only')]:
            with self.subTest(event_type=event_type):
                ScheduleEvent.objects.filter(faculty=self.faculty).delete()
                self.event(event_type)
                self.assertEqual(self.status_at(9, 15), expected)

    def test_manual_override_still_wins(self):
        self.event('unavailable')
        self.faculty.manual_status_override = True
        self.faculty.manual_status = 'available'
        self.faculty.save(update_fields=['manual_status_override', 'manual_status'])
        self.assertEqual(self.status_at(9, 15), 'available')

    def test_recurring_unavailable_event_uses_same_mapping(self):
        event = self.event('unavailable')
        event.date = None
        event.day_of_week = 'monday'
        event.start_month = event.end_month = 11
        event.save()
        self.assertEqual(self.status_at(9, 15), 'unavailable')
        self.assertEqual(self.status_at(10), 'not_set')

    def test_other_school_events_and_subscriptions_do_not_affect_transition(self):
        operator = User.objects.create_user(username='mapping-operator', role='systemadmin')
        other = School(name='Other Mapping School', code='MAPOTHER')
        other.save(actor=operator)
        other_user = User.objects.create_user(username='mapping-other-faculty', role='faculty', school=other)
        other_faculty = FacultyProfile.objects.create(user=other_user, faculty_id='mapping-other', college_id='CCS')
        ScheduleEvent.objects.create(faculty=other_faculty, title='Foreign leave', event_type='on-leave',
            date=date(2026, 11, 2), start_time=time(9), end_time=time(10))
        own_student = User.objects.create_user(username='mapping-own-student', role='student', school=self.school)
        other_student = User.objects.create_user(username='mapping-other-student', role='student', school=other)
        FacultyStatusSubscription.objects.create(student=own_student, faculty=self.faculty)
        FacultyStatusSubscription.objects.create(student=other_student, faculty=other_faculty)
        self.event('unavailable')
        self.assertEqual(self.status_at(9, 15), 'unavailable')
        self.assertEqual(list(Notification.objects.values_list('recipient_id', flat=True)), [own_student.pk])
        self.assertFalse(StatusHistory.objects.filter(faculty=other_faculty).exists())

    def test_repeated_refresh_does_not_duplicate_transition_notifications(self):
        student = User.objects.create_user(username='mapping-follower', role='student', school=self.school)
        FacultyStatusSubscription.objects.create(student=student, faculty=self.faculty)
        self.event('unavailable')
        self.assertEqual(self.status_at(9, 15), 'unavailable')
        self.assertEqual(self.status_at(9, 20), 'unavailable')
        self.assertEqual(StatusHistory.objects.filter(faculty=self.faculty, status='unavailable').count(), 1)
        self.assertEqual(Notification.objects.filter(recipient=student).count(), 1)
