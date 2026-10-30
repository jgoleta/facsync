"""Read-only availability inferred from recorded schedule gaps."""

from apps.core.school_scope import school_service, current_school

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db.models import Prefetch
from django.utils import timezone

from apps.faculty.models import ScheduleEvent
from .analytics import _eligible_faculty
from apps.faculty.services.schedule_conflicts import (
    eligible_schedule_events, schedule_intervals, WORK_START, WORK_END,
)


SCHEDULE_RANK_NOTE = (
    'These totals cover 8 AM–5 PM. All ties are included. '
    'Faculty without recorded schedules are excluded. '
    'Open schedule time does not guarantee availability; check with the faculty member before visiting.'
)


def _open_minutes(events, day):
    window_start = datetime.combine(day, WORK_START)
    window_end = datetime.combine(day, WORK_END)
    intervals = []
    for event in events:
        for start, end in schedule_intervals(event, day):
            start, end = max(start, window_start), min(end, window_end)
            if start < end:
                intervals.append((start, end))
    cursor = window_start
    gaps = []
    for start, end in sorted(intervals):
        if start > cursor:
            gaps.append((start - cursor).total_seconds() / 60)
        cursor = max(cursor, end)
    if cursor < window_end:
        gaps.append((window_end - cursor).total_seconds() / 60)
    return sum(gaps)


@school_service
def get_schedule_availability(college_code, *, today=None):
    """Summarize the current local week for active faculty in one college.

    Faculty without eligible schedule records cannot win the ranking.
    """
    timezone_name = getattr(settings, 'GOOGLE_CALENDAR_TIME_ZONE', settings.TIME_ZONE)
    today = today or timezone.localtime(timezone.now(), ZoneInfo(timezone_name)).date()
    week_start = today - timedelta(days=today.weekday())
    events = eligible_schedule_events()
    faculty = list(_eligible_faculty(college_code).select_related('user').order_by('faculty_id').prefetch_related(
        Prefetch('schedule_events', queryset=events, to_attr='availability_events')
    )) if str(college_code or '').strip() else []
    rows = []
    for offset, (_, label) in enumerate(ScheduleEvent.WEEKDAY_CHOICES):
        day = week_start + timedelta(days=offset)
        candidates = []
        for profile in faculty:
            open_minutes = _open_minutes(profile.availability_events, day)
            if profile.availability_events:
                candidates.append((profile, open_minutes))
        best = max((minutes for _, minutes in candidates), default=0)
        winners = [
            profile.user.get_full_name() or profile.user.username
            for profile, minutes in candidates if minutes == best and best > 0
        ]
        rows.append({
            'day': label,
            'date': day,
            'winners': winners,
            'open_minutes': best,
            'open_display': f'{int(best // 60)}h {int(best % 60)}m',
            'ranking_empty': 'No open time' if candidates else 'No recorded schedules',
        })
    return {
        'rows': rows,
        'faculty_count': len(faculty),
        'week_start': week_start,
        'week_end': week_start + timedelta(days=6),
        'timezone': timezone_name,
    }
