"""Read-only availability inferred from recorded schedule gaps."""

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db.models import Prefetch, Q
from django.utils import timezone

from apps.faculty.models import ScheduleEvent
from .analytics import _eligible_faculty


WORK_START = time(8)
WORK_END = time(17)
MIN_FREE_MINUTES = 60


def _occurs_on(event, day):
    if event.date is not None:
        return event.date == day
    if event.day_of_week != ScheduleEvent.WEEKDAY_CHOICES[day.weekday()][0]:
        return False
    if day.isoformat() in (event.recurrence_excluded_dates or []):
        return False
    if event.recurrence_start_date and day < event.recurrence_start_date:
        return False
    if event.recurrence_end_date and day > event.recurrence_end_date:
        return False
    if event.start_month and event.end_month:
        if event.start_month <= event.end_month:
            return event.start_month <= day.month <= event.end_month
        return day.month >= event.start_month or day.month <= event.end_month
    return True


def _open_time(events, day):
    window_start = datetime.combine(day, WORK_START)
    window_end = datetime.combine(day, WORK_END)
    intervals = []
    for event in events:
        # Include yesterday's occurrences to capture overnight spillover.
        for occurrence in (day - timedelta(days=1), day):
            if not _occurs_on(event, occurrence):
                continue
            if event.start_time is None:
                start = datetime.combine(occurrence, time.min)
                end = start + timedelta(days=1)
            else:
                start = datetime.combine(occurrence, event.start_time)
                end = datetime.combine(occurrence, event.end_time or event.start_time)
                if end <= start:
                    end += timedelta(days=1)
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
    return sum(gaps), max(gaps, default=0)


def get_schedule_availability(college_code, *, today=None):
    """Summarize the current local week for active faculty in one college.

    Faculty without eligible schedule records count as unscheduled in the
    college percentage, but cannot win the most-available ranking.
    """
    timezone_name = getattr(settings, 'GOOGLE_CALENDAR_TIME_ZONE', settings.TIME_ZONE)
    today = today or timezone.localtime(timezone.now(), ZoneInfo(timezone_name)).date()
    week_start = today - timedelta(days=today.weekday())
    events = ScheduleEvent.objects.filter(
        Q(google_event_id__isnull=True) | Q(managed_by_facsync=True) | Q(sync_state='synced')
    )
    faculty = list(_eligible_faculty(college_code).select_related('user').order_by('faculty_id').prefetch_related(
        Prefetch('schedule_events', queryset=events, to_attr='availability_events')
    )) if str(college_code or '').strip() else []
    rows = []
    for offset, (_, label) in enumerate(ScheduleEvent.WEEKDAY_CHOICES):
        day = week_start + timedelta(days=offset)
        candidates = []
        available_count = 0
        for profile in faculty:
            open_minutes, longest_gap = _open_time(profile.availability_events, day)
            available_count += longest_gap >= MIN_FREE_MINUTES
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
            'available_count': available_count,
            'availability_percent': round(100 * available_count / len(faculty)) if faculty else None,
        })
    return {
        'rows': rows,
        'faculty_count': len(faculty),
        'week_start': week_start,
        'week_end': week_start + timedelta(days=6),
        'timezone': timezone_name,
    }
