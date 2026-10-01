"""Student-only, read-only availability answers. No performance metrics or AI."""
from zoneinfo import ZoneInfo
from django.conf import settings
from django.urls import reverse
from django.utils import timezone
from apps.core.models import OfficeClosure
from apps.core.department_updates import UPDATE_QUESTIONS, department_update_answer
from apps.depthead.services.analytics import _eligible_faculty
from apps.depthead.services.schedule_availability import get_schedule_availability

QUESTIONS = {
    'available_now': 'Which faculty are available right now?',
    'today_open': 'Which faculty have the most open schedule time today?',
    'week_daily': 'Who has the most open schedule time each day this week?',
    'best_day': 'Which day this week has the most faculty availability?',
    **UPDATE_QUESTIONS,
}


def availability_answer(metric, college):
    if metric not in QUESTIONS:
        raise ValueError('Unknown availability question')
    if metric in UPDATE_QUESTIONS:
        return department_update_answer(metric, college, 'student', reverse('students:dashboard'))
    tz = getattr(settings, 'GOOGLE_CALENDAR_TIME_ZONE', settings.TIME_ZONE)
    today = timezone.localtime(timezone.now(), ZoneInfo(tz)).date()
    period = f'Today: {today} ({tz})'
    note = 'Latest recorded status; availability may change. Check with the faculty member before visiting.'
    closed = OfficeClosure.objects.filter(college__iexact=college, is_closed=True).exists()
    if metric == 'available_now':
        if closed:
            lines = ['Your college is currently closed.']
        else:
            faculty = _eligible_faculty(college).filter(current_status='available').select_related('user').order_by('faculty_id')
            lines = [p.user.get_full_name() or p.user.username for p in faculty]
            lines = lines or ['No faculty are currently recorded as Available in your college.']
    else:
        data = get_schedule_availability(college, today=today)
        period = f"This week: {data['week_start']} to {data['week_end']} ({data['timezone']})"
        note = '8am-5pm. Ranked by total unscheduled time; all ties shown. Faculty without recorded schedules are excluded. Free time does not guarantee availability.'
        rows = data['rows']
        if metric == 'today_open':
            rows = [row for row in rows if row['date'] == today]
            period = f'Today: {today} ({tz})'
        if metric == 'best_day':
            note = '8am-5pm. Counts faculty with at least 60 consecutive unscheduled minutes. Faculty without recorded schedules count as fully unscheduled. All tied days are shown. Free time does not guarantee availability.'
            best = max((row['available_count'] for row in rows), default=0)
            lines = [f"{row['day']} ({row['date']}): {row['available_count']} of {data['faculty_count']} faculty."
                     for row in rows if row['available_count'] == best] if best else ['No qualifying schedule availability recorded this week.']
        else:
            lines = [f"{row['day']} ({row['date']}): " +
                     (f"{', '.join(row['winners'])} - {row['open_display']} per faculty."
                      if row['winners'] else row['ranking_empty']) for row in rows]
        if not data['faculty_count']:
            lines = ['No active faculty in your college.']
        if closed:
            note = 'Your college is currently closed. These schedule estimates do not override the closure. ' + note
    return {'period': period, 'lines': lines, 'note': note,
            'source_url': reverse('students:dashboard')}
