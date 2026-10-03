"""Student-only, read-only availability answers. No performance metrics or AI."""
from zoneinfo import ZoneInfo
from django.conf import settings
from django.urls import reverse
from django.utils import timezone
from apps.core.models import OfficeClosure
from apps.core.department_updates import UPDATE_QUESTIONS, department_update_answer
from apps.core.chat_presentation import answer, date_label, date_range, duration
from apps.depthead.services.analytics import _eligible_faculty
from apps.depthead.services.schedule_availability import (
    get_schedule_availability, SCHEDULE_COUNT_NOTE, SCHEDULE_RANK_NOTE,
)

QUESTIONS = {
    'available_now': 'Which faculty are available right now?',
    'today_open': 'Which faculty have the most open schedule time today?',
    'week_daily': 'Who has the most open schedule time each day this week?',
    'best_day': 'Which day this week has the most faculty with at least two consecutive hours of open schedule time?',
    **UPDATE_QUESTIONS,
}


def availability_answer(metric, college):
    if metric not in QUESTIONS:
        raise ValueError('Unknown availability question')
    source = reverse('students:dashboard')
    if metric in UPDATE_QUESTIONS:
        return department_update_answer(metric, college, 'student', source)
    tz = getattr(settings, 'GOOGLE_CALENDAR_TIME_ZONE', settings.TIME_ZONE)
    today = timezone.localtime(timezone.now(), ZoneInfo(tz)).date()
    closed = OfficeClosure.objects.filter(college__iexact=college, is_closed=True).exists()
    if metric == 'available_now':
        note = 'These are based on their latest recorded status. Check with the faculty member before visiting.'
        if closed:
            return answer('', ['Your college is currently marked as closed.'],
                          'Check with your college before visiting.', source, 'View faculty directory', paragraphs=True)
        faculty = _eligible_faculty(college).filter(current_status='available').select_related('user').order_by('faculty_id')
        lines = [p.user.get_full_name() or p.user.username for p in faculty]
        return answer(f'The following faculty in your college are available right now, {date_label(today)}:',
                      lines, note, source, 'View faculty directory',
                      empty=f'No faculty in your college are currently marked as available as of {date_label(today)}.')

    data = get_schedule_availability(college, today=today)
    week = date_range(data['week_start'], data['week_end'])
    rows = data['rows']
    note = SCHEDULE_RANK_NOTE
    empty = 'There are no active faculty in your college to compare.'
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
    else:
        intro = f'These days have the most faculty with at least two consecutive hours of open schedule time this week, {week}:'
        note = SCHEDULE_COUNT_NOTE + ' All tied days are shown.'
        best = max((row['available_count'] for row in rows), default=0)
        lines = [f"{row['day']}, {date_label(row['date'])} — {row['available_count']} of {data['faculty_count']} faculty"
                 for row in rows if row['available_count'] == best] if best else []
        if data['faculty_count']:
            empty = 'No faculty have a recorded schedule gap of at least two consecutive hours between 8 AM and 5 PM this week.'
    if not data['faculty_count']:
        lines = []
    if closed:
        note = 'Your college is currently closed. These schedule estimates do not override the closure. ' + note
    return answer(intro, lines, note, source, 'View faculty directory', empty=empty)
