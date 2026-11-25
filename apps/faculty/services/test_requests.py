"""Shared, email-free preparation of explicitly selected Faculty test batches."""
from datetime import datetime, time, timedelta
from hashlib import sha256
from zoneinfo import ZoneInfo

from django.conf import settings
from django.core.management.base import CommandError
from django.utils import timezone

from apps.core.department_access import faculty_closed
from apps.core.education import YEAR_CHOICES
from apps.core.models import Department, User
from apps.core.role_access import has_role
from apps.core.student_access import StudentEligibility, profile_ready
from apps.faculty.constants import CONSULTATION_NOTE_MAX_LENGTH
from apps.faculty.models import ConsultationRequest, FacultyProfile, GoogleCalendarConnection
from .consultation_conflicts import booking_conflict_payload
from .google_calendar import GoogleCalendarError, list_google_events

ZONE = ZoneInfo('Asia/Manila')
WEEKDAYS = {'mon': 0, 'tue': 1, 'wed': 2, 'thu': 3, 'fri': 4, 'sat': 5}
TASKS = (
    ('5A', 'Approve', 'Please approve this consultation request.'),
    ('5B', 'Decline', 'Please decline this consultation request. You may add a sample faculty note.'),
    ('5C', 'Approve, then cancel', 'Please approve this request, then select Cancel Consultation.'),
    ('5D', 'Approve, then complete', 'Please approve this request, then select Mark as Completed.'),
)


class TestRequestBuilder:
    def _faculty(self, email):
        matches = list(User.objects.filter(email__iexact=email).select_related('school', 'department__college')[:2])
        if len(matches) != 1:
            raise CommandError('Expected exactly one account with that email. An invitation alone is not a completed account.')
        user = matches[0]
        if (not user.is_active or user.account_status != 'active' or not has_role(user, 'faculty')
                or not user.school_id or not user.school.is_active or not user.profile_completed):
            raise CommandError('Faculty must be active and have completed their profile in an active school.')
        faculty = FacultyProfile.objects.filter(user=user).first()
        if faculty is None:
            raise CommandError('Faculty profile is not ready. Ask the tester to finish first-time setup.')
        faculty.user = user
        if faculty.current_status == 'on_leave' or faculty_closed(faculty):
            raise CommandError('Faculty is on leave or their unit is closed; requests were not created.')
        return faculty

    def _student(self, faculty):
        owner = faculty.user
        username = f'facsync_test_student_{owner.school_id}_{owner.pk}'
        if User._base_manager.filter(username=username).exists():
            raise CommandError('A test batch was already prepared for this faculty (reserved dummy Student exists). No duplicate batch created.')
        # Try the faculty's home level first; shared offices may serve multiple levels.
        for level in ('shs', 'jhs', 'elementary', 'college'):
            if level not in owner.school.educational_levels:
                continue
            department = None
            if level == 'college':
                department = owner.department
                if department is None:
                    department = next((d for d in Department.objects.filter(is_active=True).select_related('college')
                        if 'college' in d.student_levels and (not d.college_id or d.college.is_active)), None)
                if department is None:
                    continue
            student = User(username=username, email='', first_name='FacSync Test', last_name='Student',
                school=owner.school, role='student', account_status='active', is_active=True,
                profile_completed=True, student_id=f'TEST-{owner.pk}', educational_level=level,
                year_level=YEAR_CHOICES[level][0][0], department=department,
                college=(department.college.code if department and department.college_id else ''))
            student.set_unusable_password()
            if profile_ready(student) and StudentEligibility(student).allows(faculty):
                return student
        raise CommandError('No eligible dummy Student level/department is available. Review the faculty unit served levels.')

    def _plan(self, faculty, start, days, *, weekdays=None, start_time=None, duration=60):
        slots = []
        # One calendar window per plan, not a remote call for every candidate slot.
        google_events = None
        connection = GoogleCalendarConnection.objects.filter(user_id=faculty.user_id).first()
        if connection is not None:
            zone = ZoneInfo(getattr(settings, 'GOOGLE_CALENDAR_TIME_ZONE', settings.TIME_ZONE))
            try:
                google_events = list(list_google_events(connection,
                    time_min=datetime.combine(start, time.min, zone).isoformat(),
                    time_max=datetime.combine(start + timedelta(days=days), time.min, zone).isoformat()))
            except GoogleCalendarError as error:
                raise CommandError('Unable to verify Google Calendar availability; no test requests created.') from error
        allowed_days = set(range(6)) if weekdays is None else {WEEKDAYS[value] for value in weekdays}
        starts = [start_time] if start_time is not None else [time(hour) for hour in range(9, 17)]
        for offset in range(days):
            day = start + timedelta(days=offset)
            if day.weekday() not in allowed_days:
                continue
            for begin in starts:
                end = (datetime.combine(day, begin) + timedelta(minutes=duration)).time()
                if end > time(17):
                    continue
                if datetime.combine(day, begin, ZONE) <= timezone.now():
                    continue
                conflict = booking_conflict_payload(faculty, day, begin, end, 'face_to_face',
                    google_events=google_events)
                if conflict and conflict.get('availability_check_failed'):
                    raise CommandError('Unable to verify Google Calendar availability; no test requests created.')
                if conflict:
                    continue
                # Pending requests do not reserve slots, but avoid them for this batch.
                if ConsultationRequest.objects.filter(faculty=faculty, date=day,
                    status='pending', start_time__lt=end, end_time__gt=begin).exists():
                    continue
                slots.append((day, begin, end))
                if len(slots) == len(TASKS):
                    return slots
        raise CommandError('Could not find four free slots. Try a later --start-date or a larger --days window.')


    def create_requests(self, locked, student, slots):
        school = locked.user.school
        student.full_clean()
        student.save()
        for (label, _, instruction), (day, begin, end) in zip(TASKS, slots):
            message = f'FacSync testing - Task {label}: {instruction} This is a test only; no actual meeting is required.'
            if len(message) > CONSULTATION_NOTE_MAX_LENGTH:
                raise CommandError('Testing message exceeds the consultation note limit.')
            key = sha256(f'{school.pk}:{locked.user_id}:{locked.pk}:{label}'.encode()).hexdigest()[:48]
            ConsultationRequest.objects.create(request_id=f'fctest_{key}', user=student,
                faculty=locked, date=day, start_time=begin, end_time=end, agenda='general_concern',
                consultation_type='face_to_face', status='pending', student_message=message, faculty_note='')
