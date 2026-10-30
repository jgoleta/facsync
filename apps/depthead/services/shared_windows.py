"""Read-only, college-scoped meeting planning for the current working week."""

from apps.core.school_scope import school_service, current_school
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db.models import Prefetch
from django.utils import timezone

from apps.faculty.models import ConsultationRequest
from apps.faculty.services.schedule_conflicts import (
    eligible_schedule_events, occurs_on, schedule_intervals,
    occurrence_interval, overlaps, merge_intervals, WORK_START, WORK_END,
)
from .analytics import _eligible_faculty

DURATION_CHOICES = ((30, '30 minutes'), (60, '1 hour'), (120, '2 hours'),
                    (240, '4 hours'), (540, 'Full working day (9 hours)'))


def planning_week(now=None):
    tz_name = getattr(settings, 'GOOGLE_CALENDAR_TIME_ZONE', settings.TIME_ZONE)
    local_now = timezone.localtime(now or timezone.now(), ZoneInfo(tz_name))
    monday = local_now.date() - timedelta(days=local_now.weekday())
    return {
        'now': local_now, 'today': local_now.date(), 'week_start': monday,
        'week_end': monday + timedelta(days=4), 'timezone': tz_name,
        'ended': local_now.weekday() >= 5,
    }


@school_service
def find_shared_windows(college_code, day, duration_minutes, *, now=None):
    week = planning_week(now)
    if (not week['week_start'] <= day <= week['week_end']
            or (not week['ended'] and day < week['today'])):
        raise ValueError('Choose a remaining Monday–Friday date in the current week.')
    if duration_minutes not in dict(DURATION_CHOICES):
        raise ValueError('Choose a supported event duration.')
    result = dict(week, date=day, duration_minutes=duration_minutes,
                  faculty_count=0, best_count=0, windows=[], message='')
    if not str(college_code or '').strip():
        result['message'] = 'No active faculty in your college.'
        return result
    consultations = ConsultationRequest.objects.filter(
        date__in=[day - timedelta(days=1), day],
        status__in=['approved', 'cancellation_requested'],
    )
    faculty = list(_eligible_faculty(college_code).select_related('user').order_by('faculty_id').prefetch_related(
        Prefetch('schedule_events', queryset=eligible_schedule_events(), to_attr='planning_events'),
        Prefetch('consultation_requests', queryset=consultations, to_attr='planning_consultations'),
    ))
    result['faculty_count'] = len(faculty)
    if not faculty:
        result['message'] = 'No active faculty in your college.'
        return result
    roster = []
    for profile in faculty:
        # Records on another weekday do not establish knowledge of this day.
        known = any(occurs_on(event, day) for event in profile.planning_events)
        intervals = [interval for event in profile.planning_events
                     for interval in schedule_intervals(event, day)]
        intervals.extend(occurrence_interval(row.date, row.start_time, row.end_time)
                         for row in profile.planning_consultations)
        roster.append((profile, known, merge_intervals(intervals)))
    start = datetime.combine(day, WORK_START)
    work_end = datetime.combine(day, WORK_END)
    duration = timedelta(minutes=duration_minutes)
    # Weekend searches review this week's recorded windows without locking the form.
    local_now = start if week['ended'] else week['now'].replace(tzinfo=None)
    candidates = []
    while start + duration <= work_end:
        end = start + duration
        if start >= local_now:
            groups = {'free': [], 'conflict': [], 'unknown': []}
            for profile, known, intervals in roster:
                group = ('conflict' if any(overlaps(start, end, a, b) for a, b in intervals)
                         else 'free' if known else 'unknown')
                groups[group].append({'id': profile.pk,
                                     'name': profile.user.get_full_name() or profile.user.username})
            candidates.append(dict(groups, start=start, end=end, free_count=len(groups['free']),
                                   conflict_count=len(groups['conflict']), unknown_count=len(groups['unknown'])))
        start += timedelta(minutes=15)
    if not candidates:
        result['message'] = 'No remaining time window fits this duration today.'
        return result
    best = max(row['free_count'] for row in candidates)
    result['best_count'] = best
    if not best:
        result['message'] = ('All faculty have unknown schedules for this date.'
                             if all(row['unknown_count'] == len(faculty) for row in candidates)
                             else 'No window has any faculty known to be free for the full duration.')
    elif best < len(faculty):
        result['message'] = 'No window has all faculty known to be free. These windows have the highest free headcount.'
    # Preserve every tied candidate. Collapse only adjacent starts with exactly
    # the same membership, not just the same counts.
    for row in candidates:
        if row['free_count'] != best:
            continue
        previous = result['windows'][-1] if result['windows'] else None
        if (previous and row['start'] == previous['latest_start'] + timedelta(minutes=15)
                and all(previous[key] == row[key] for key in ('free', 'conflict', 'unknown'))):
            previous['latest_start'] = row['start']
            previous['latest_end'] = row['end']
        else:
            result['windows'].append(dict(row, latest_start=row['start'], latest_end=row['end']))
    return result
