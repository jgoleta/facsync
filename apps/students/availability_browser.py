"""Student-only, read-only availability answers. No performance metrics or AI."""

from apps.core.school_scope import school_service, current_school
from zoneinfo import ZoneInfo
from django.conf import settings
from django.urls import reverse
from django.utils import timezone
from apps.core.models import OfficeClosure
from apps.depthead.scope import DepartmentScope
from django.db.models import Q
from apps.core.department_updates import UPDATE_QUESTIONS, department_update_answer
from apps.core.chat_presentation import answer, date_label, date_range, duration
from apps.depthead.services.analytics import _eligible_faculty
from apps.depthead.services.schedule_availability import (
    get_schedule_availability, SCHEDULE_RANK_NOTE,
)

QUESTIONS = {
    'available_now': 'Which faculty are available right now?',
    'today_open': 'Which faculty have the most open schedule time today?',
    'week_daily': 'Who has the most open schedule time each day this week?',
    'active_announcements': 'Which announcements apply to me?',
    'college_closure': 'Which departments are closed for bookings?',
}


@school_service
def availability_answer(metric, college, *, student=None):
    if metric not in QUESTIONS:
        raise ValueError('Unknown availability question')
    source = reverse('students:dashboard')
    if metric in UPDATE_QUESTIONS:
        return department_update_answer(metric, college, 'student', source, student=student)
    tz = getattr(settings, 'GOOGLE_CALENDAR_TIME_ZONE', settings.TIME_ZONE)
    basic = student is not None and student.educational_level != 'college'
    label = 'departments and offices serving your educational level' if student is not None else 'your department' if isinstance(college, DepartmentScope) else 'your college'
    today = timezone.localtime(timezone.now(), ZoneInfo(tz)).date()
    closed = OfficeClosure.objects.filter(department_id__in=college.department_ids, is_closed=True).exists() if isinstance(college, DepartmentScope) else OfficeClosure.objects.filter(department__isnull=True, college__iexact=college, is_closed=True).exists()
    if metric == 'available_now':
        note = 'These are based on their latest recorded status. Check with the faculty member before visiting.'
        if closed and student is None:
            return answer('', [f'{label.capitalize()} is currently marked as closed.'],
                          f'Check with {label} before visiting.', source, 'View faculty directory', paragraphs=True)
        faculty = _eligible_faculty(college).filter(current_status='available').select_related('user').order_by('faculty_id')
        if isinstance(college, DepartmentScope):
            faculty = faculty.exclude(user__department__closure__is_closed=True).exclude(Q(
                user__department__isnull=True, college_id__in=OfficeClosure.objects.filter(
                    department__isnull=True, is_closed=True).values_list('college', flat=True)))
        lines = [p.user.get_full_name() or p.user.username for p in faculty]
        return answer(f'The following faculty in {label} are available right now, {date_label(today)}:',
                      lines, note, source, 'View faculty directory',
                      empty=f'No faculty in {label} are currently marked as available as of {date_label(today)}.')

    data = get_schedule_availability(college, today=today)
    week = date_range(data['week_start'], data['week_end'])
    rows = data['rows']
    note = SCHEDULE_RANK_NOTE
    empty = f'There are no active faculty in {label} to compare.'
    if metric == 'today_open':
        rows = [row for row in rows if row['date'] == today]
        intro = f'These faculty have the most open time in their recorded schedules today, {date_label(today)}:'
        lines = [f"{name} — {duration(row['open_minutes'])}" for row in rows for name in row['winners']]
        if data['faculty_count']:
            empty = ('There are no recorded schedules to compare today.' if not rows or rows[0]['ranking_empty'] == 'No recorded schedules'
                     else 'There is no open schedule time between 8 AM and 5 PM today.')
    elif metric == 'week_daily':
        intro = f'Here are the faculty with the most open schedule time each day this week, {week}:'
        lines = []
        for row in rows:
            value = (f"{', '.join(row['winners'])} — {duration(row['open_minutes'])}" + (' each' if len(row['winners']) > 1 else '')
                     if row['winners'] else ('No recorded schedules to compare' if row['ranking_empty'] == 'No recorded schedules' else 'No open schedule time'))
            lines.append(f"{row['day']}, {date_label(row['date'])}: {value}")
    if not data['faculty_count']:
        lines = []
    if closed:
        note = ('Some eligible departments or offices are currently closed. ' if student is not None else f'{label.capitalize()} is currently closed. ') + 'These schedule estimates do not override closures. ' + note
    return answer(intro, lines, note, source, 'View faculty directory', empty=empty)
