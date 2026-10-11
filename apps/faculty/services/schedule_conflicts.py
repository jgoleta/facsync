"""Pure occurrence and interval rules shared by status and schedule planning."""
from datetime import datetime, time, timedelta

from django.db.models import Q

from apps.faculty.models import ScheduleEvent

WORK_START = time(8)
WORK_END = time(17)


def eligible_schedule_events():
    return ScheduleEvent.objects.filter(
        Q(google_event_id__isnull=True) | Q(managed_by_facsync=True) | Q(sync_state='synced')
    )


def occurs_on(event, day):
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


def occurrence_interval(day, start_time, end_time):
    if start_time is None:
        start = datetime.combine(day, time.min)
        return start, start + timedelta(days=1)
    start = datetime.combine(day, start_time)
    end = datetime.combine(day, end_time or start_time)
    if end <= start:
        end += timedelta(days=1)
    return start, end


def schedule_intervals(event, day):
    """Include the previous occurrence for overnight spillover into this day."""
    for occurrence in (day - timedelta(days=1), day):
        if occurs_on(event, occurrence):
            yield occurrence_interval(occurrence, event.start_time, event.end_time)


def overlaps(start, end, other_start, other_end):
    return start < other_end and end > other_start


def merge_intervals(intervals):
    merged = []
    for start, end in sorted(intervals):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    return merged
