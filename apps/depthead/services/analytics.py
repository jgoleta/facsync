
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.db.models import Count, Q, OuterRef, Subquery
from django.utils import timezone

from apps.core.models import College
from apps.faculty.models import ConsultationRequest, FacultyProfile, StatusHistory, WalkInQueue


DEFAULT_ANALYTICS_TIMEZONE = "Asia/Manila"
WEEKDAY_NAMES = (
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
)


@dataclass(frozen=True)
class NormalizedPeriod:
    """Internal representation of one inclusive local-date analytics period."""

    start_date: date
    end_date: date
    generated_at: datetime
    timezone_name: str
    timezone: ZoneInfo
    start_datetime: datetime
    end_datetime_exclusive: datetime
    is_complete: bool

    @property
    def duration_days(self):
        return (self.end_date - self.start_date).days + 1

    def as_dict(self):
        return {
            "start_date": self.start_date.isoformat(),
            "end_date": self.end_date.isoformat(),
            "generated_at": self.generated_at.isoformat(),
            "timezone": self.timezone_name,
            "inclusive_dates": True,
            "is_complete": self.is_complete,
            "duration_days": self.duration_days,
        }


def _coerce_date(value, field_name):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be a date or ISO date string.") from exc


def normalize_period(
    start_date=None,
    end_date=None,
    timezone_name=DEFAULT_ANALYTICS_TIMEZONE,
):
    """Normalize optional inputs into inclusive local dates and aware bounds.

    When no range is supplied, the selected period is month-to-date in the
    requested analytics timezone. Timestamp queries use an inclusive start and
    exclusive next-day boundary so the local end date is fully included.
    """

    try:
        analytics_timezone = ZoneInfo(timezone_name)
    except (TypeError, ZoneInfoNotFoundError) as exc:
        raise ValueError(f"Unknown analytics timezone: {timezone_name}") from exc

    generated_at = timezone.now().astimezone(analytics_timezone)
    local_today = generated_at.date()
    normalized_end = _coerce_date(end_date, "end_date") or local_today
    normalized_start = _coerce_date(start_date, "start_date")
    if normalized_start is None:
        normalized_start = normalized_end.replace(day=1)
    if normalized_start > normalized_end:
        raise ValueError("start_date must be on or before end_date.")

    start_datetime = datetime.combine(
        normalized_start,
        time.min,
        tzinfo=analytics_timezone,
    )
    end_datetime_exclusive = datetime.combine(
        normalized_end + timedelta(days=1),
        time.min,
        tzinfo=analytics_timezone,
    )
    return NormalizedPeriod(
        start_date=normalized_start,
        end_date=normalized_end,
        generated_at=generated_at,
        timezone_name=timezone_name,
        timezone=analytics_timezone,
        start_datetime=start_datetime,
        end_datetime_exclusive=end_datetime_exclusive,
        is_complete=normalized_end < local_today,
    )


def current_week_period():
    today = timezone.now().astimezone(ZoneInfo(DEFAULT_ANALYTICS_TIMEZONE)).date()
    monday = today - timedelta(days=today.weekday())
    return normalize_period(monday, monday + timedelta(days=6))


def get_hourly_availability_snapshot(college_code):
    """Read persisted statuses and appointments; never refresh status or Calendar."""
    if not str(college_code or '').strip():
        raise ValueError('college_code is required.')
    now = timezone.now().astimezone(ZoneInfo(DEFAULT_ANALYTICS_TIMEZONE))
    start = now.replace(minute=0, second=0, microsecond=0)
    end = start + timedelta(hours=1)
    names = [profile.user.get_full_name() or profile.user.username
             for profile in _eligible_faculty(college_code).filter(
                 current_status='available', user__is_active=True,
             ).select_related('user').order_by('user__first_name', 'user__last_name', 'faculty_id')]
    counts = Counter()
    for row in get_base_consultation_queryset(college_code).filter(
        date=start.date(), status__in=['approved', 'pending'],
        start_time__isnull=False, end_time__isnull=False,
    ).only('date', 'start_time', 'end_time', 'status'):
        appointment_start = datetime.combine(row.date, row.start_time, tzinfo=start.tzinfo)
        appointment_end = datetime.combine(row.date, row.end_time, tzinfo=start.tzinfo)
        if appointment_start < end and appointment_end > start:
            counts[row.status] += 1
    return {
        'period_label': f"Today, {start.strftime('%B')} {start.day} \u00b7 {start.strftime('%I:%M %p').lstrip('0')}\u2013{end.strftime('%I:%M %p').lstrip('0')} \u00b7 {DEFAULT_ANALYTICS_TIMEZONE}",
        'available_count': len(names), 'available_names': names,
        'approved_count': counts['approved'], 'pending_count': counts['pending'],
    }


def _percentage(numerator, denominator):
    if not denominator:
        return None
    return round((numerator / denominator) * 100, 2)


def _peak(counter):
    if not counter:
        return [], 0
    peak_count = max(counter.values())
    if peak_count <= 0:
        return [], 0
    return sorted(key for key, count in counter.items() if count == peak_count), peak_count


def _status_keys(choices):
    return [value for value, _label in choices]


def get_base_consultation_queryset(college_code, period=None):
    """Return the canonical college-scoped consultation queryset."""

    if not str(college_code or "").strip():
        raise ValueError("college_code is required.")
    queryset = ConsultationRequest.objects.filter(
        faculty__college_id__iexact=str(college_code).strip()
    )
    if period is not None:
        queryset = queryset.filter(
            date__gte=period.start_date,
            date__lte=period.end_date,
        )
    return queryset


def _consultation_rows(consultations):
    """Load only calculation fields once, or reuse an existing request snapshot."""
    if isinstance(consultations, list):
        return consultations
    return list(consultations.only(
        'faculty_id', 'user_id', 'status', 'agenda', 'date',
        'start_time', 'end_time', 'requested_at', 'approved_at',
    ))


def get_consultation_summary(consultations):
    """Return status, agenda, completion, and approval-delay aggregates."""

    consultations = _consultation_rows(consultations)
    total = len(consultations)
    status_distribution = {
        key: 0 for key in _status_keys(ConsultationRequest.STATUS_CHOICES)
    }
    status_distribution.update(Counter(row.status for row in consultations))

    agenda_distribution = {
        key: 0 for key in _status_keys(ConsultationRequest.AGENDA_CHOICES)
    }
    agenda_distribution.update(Counter(row.agenda for row in consultations))

    completed = status_distribution.get("completed", 0)
    resolved_denominator = sum(
        status_distribution.get(status, 0)
        for status in ("completed", "declined", "cancelled")
    )

    response_durations = []
    for row in consultations:
        if row.approved_at is None:
            continue
        duration = row.approved_at - row.requested_at
        if duration.total_seconds() >= 0:
            response_durations.append(duration.total_seconds() / 3600)

    average_response_hours = (
        round(sum(response_durations) / len(response_durations), 2)
        if response_durations
        else None
    )

    return {
        "total_records": total,
        "status_distribution": status_distribution,
        "agenda_distribution": agenda_distribution,
        "completion": {
            "completed_count": completed,
            "overall_denominator": total,
            "overall_rate_percent": _percentage(completed, total),
            "resolved_denominator": resolved_denominator,
            "resolved_rate_percent": _percentage(completed, resolved_denominator),
            "resolved_statuses": ["completed", "declined", "cancelled"],
            "open_statuses_excluded_from_resolved_rate": ["pending", "approved"],
        },
        "approval_response": {
            "average_hours": average_response_hours,
            "sample_size": len(response_durations),
            "timestamp_source": "approved_at - requested_at",
            "approvals_only": True,
        },
    }


def get_scheduled_consultation_patterns(consultations):
    """Return occurrence proxies based on completed consultations' schedules."""

    completed = [row for row in _consultation_rows(consultations) if row.status == 'completed']
    hour_counts = Counter(row.start_time.hour for row in completed if row.start_time is not None)
    weekday_counts = Counter(row.date.weekday() for row in completed)
    peak_hours, peak_hour_count = _peak(hour_counts)
    peak_weekday_indexes, peak_weekday_count = _peak(weekday_counts)

    return {
        "actual_occurrence_timestamps_available": False,
        "timestamp_source": "scheduled date + start_time",
        "status_filter": ["completed"],
        "sample_size": len(completed),
        "hourly_distribution": [
            {"hour": hour, "count": hour_counts.get(hour, 0)}
            for hour in range(24)
        ],
        "peak_hour": {
            "hours": peak_hours,
            "count": peak_hour_count,
        },
        "weekday_distribution": [
            {"weekday": name, "count": weekday_counts.get(index, 0)}
            for index, name in enumerate(WEEKDAY_NAMES)
        ],
        "peak_weekday": {
            "weekdays": [WEEKDAY_NAMES[index] for index in peak_weekday_indexes],
            "count": peak_weekday_count,
        },
    }


def get_request_submission_patterns(college_code, period, *, faculty=None):
    """Aggregate request creation timestamps in the explicit local timezone."""

    requests = get_base_consultation_queryset(college_code).filter(
        requested_at__gte=period.start_datetime,
        requested_at__lt=period.end_datetime_exclusive,
    )
    if faculty is not None:
        requests = requests.filter(faculty=faculty)
    hour_counts = Counter()
    weekday_counts = Counter()
    combination_counts = Counter()
    monthly_counts = Counter()

    timestamps = list(requests.values_list("requested_at", flat=True))
    for requested_at in timestamps:
        local_requested_at = requested_at.astimezone(period.timezone)
        hour = local_requested_at.hour
        weekday = local_requested_at.weekday()
        hour_counts[hour] += 1
        weekday_counts[weekday] += 1
        combination_counts[(weekday, hour)] += 1
        monthly_counts[local_requested_at.strftime("%Y-%m")] += 1

    peak_hours, peak_hour_count = _peak(hour_counts)
    peak_weekdays, peak_weekday_count = _peak(weekday_counts)
    peak_combinations, peak_combination_count = _peak(combination_counts)

    return {
        "timestamp_source": "requested_at",
        "timezone": period.timezone_name,
        "total_submitted": len(timestamps),
        "hourly_distribution": [
            {"hour": hour, "count": hour_counts.get(hour, 0)}
            for hour in range(24)
        ],
        "peak_hour": {
            "hours": peak_hours,
            "count": peak_hour_count,
        },
        "weekday_distribution": [
            {"weekday": name, "count": weekday_counts.get(index, 0)}
            for index, name in enumerate(WEEKDAY_NAMES)
        ],
        "peak_weekday": {
            "weekdays": [WEEKDAY_NAMES[index] for index in peak_weekdays],
            "count": peak_weekday_count,
        },
        "peak_weekday_hour": {
            "combinations": [
                {
                    "weekday": WEEKDAY_NAMES[weekday],
                    "hour": hour,
                    "label": f"{WEEKDAY_NAMES[weekday]} {hour:02d}:00",
                }
                for weekday, hour in peak_combinations
            ],
            "count": peak_combination_count,
        },
        "monthly_trend": [
            {"month": month, "count": monthly_counts[month]}
            for month in sorted(monthly_counts)
        ],
    }


def _eligible_faculty(college_code):
    return FacultyProfile.objects.filter(
        user__role="faculty",
        user__account_status="active",
        college_id__iexact=college_code,
    )


def get_current_availability(college_code, *, faculty=None):
    """Return the persisted current-status snapshot for active faculty."""

    if faculty is None:
        faculty = list(_eligible_faculty(college_code).only('current_status'))
    distribution = {key: 0 for key in _status_keys(FacultyProfile.STATUS_CHOICES)}
    distribution.update(Counter(row.current_status for row in faculty))
    total = len(faculty)
    available = distribution.get("available", 0)
    return {
        "total_active_faculty": total,
        "status_distribution": distribution,
        "available_count": available,
        "availability_rate_percent": _percentage(available, total),
        "available_status_filter": ["available"],
        "virtual_only_included_in_available": False,
        "snapshot_source": "FacultyProfile.current_status",
    }


def _status_observation(faculty, window_start, window_end):
    """Integrate one faculty member's observed status over aware boundaries."""

    if window_end <= window_start:
        return None
    carry_in = StatusHistory.objects.filter(
        faculty=faculty,
        changed_at__lt=window_start,
    ).order_by("-changed_at").first()
    rows = list(
        StatusHistory.objects.filter(
            faculty=faculty,
            changed_at__gte=window_start,
            changed_at__lt=window_end,
        ).order_by("changed_at")
    )
    return _integrate_status_history(carry_in.status if carry_in else None, rows, window_start, window_end)


def _integrate_status_history(carry_status, rows, window_start, window_end):
    """Integrate preloaded history without issuing database queries."""
    if window_end <= window_start:
        return None
    if carry_status is None and not rows:
        return None

    timeline = []
    if carry_status is not None:
        timeline.append((window_start, carry_status))
    else:
        timeline.append((max(rows[0].changed_at, window_start), rows[0].status))
        rows = rows[1:]
    timeline.extend((row.changed_at, row.status) for row in rows)

    available_seconds = 0.0
    observed_seconds = 0.0
    for index, (interval_start, status) in enumerate(timeline):
        interval_end = (
            timeline[index + 1][0]
            if index + 1 < len(timeline)
            else window_end
        )
        seconds = (interval_end - interval_start).total_seconds()
        if seconds <= 0:
            continue
        observed_seconds += seconds
        if status == "available":
            available_seconds += seconds

    return {
        "available_seconds": available_seconds,
        "observed_seconds": observed_seconds,
        "has_carry_in": carry_status is not None,
    }


def _availability_history(college_code, period):
    """Fetch the roster with carry-in states, then all in-window history."""
    carry = StatusHistory.objects.filter(
        faculty_id=OuterRef('faculty_id'), changed_at__lt=period.start_datetime,
    ).order_by('-changed_at')
    faculty = list(_eligible_faculty(college_code).only('faculty_id', 'current_status').annotate(
        carry_status=Subquery(carry.values('status')[:1]),
    ).order_by('faculty_id'))
    history = defaultdict(list)
    window_end = min(period.end_datetime_exclusive, period.generated_at)
    for row in StatusHistory.objects.filter(
        faculty_id__in=[profile.faculty_id for profile in faculty],
        changed_at__gte=period.start_datetime, changed_at__lt=window_end,
    ).only('faculty_id', 'status', 'changed_at').order_by('changed_at'):
        history[row.faculty_id].append(row)
    return faculty, history


def get_historical_availability_proxy(college_code, period, *, snapshot=None):
    """Return a faculty-time-weighted status-history availability proxy."""

    faculty, history = snapshot if snapshot is not None else _availability_history(college_code, period)
    window_start = period.start_datetime
    window_end = min(period.end_datetime_exclusive, period.generated_at)
    possible_window_seconds = max((window_end - window_start).total_seconds(), 0)
    available_seconds = 0.0
    observed_seconds = 0.0
    faculty_with_history = 0
    faculty_without_history = 0
    partial_history_faculty = 0

    for profile in faculty:
        observation = _integrate_status_history(
            profile.carry_status, history[profile.faculty_id], window_start, window_end,
        )
        if not observation or observation["observed_seconds"] <= 0:
            faculty_without_history += 1
            continue
        faculty_with_history += 1
        available_seconds += observation["available_seconds"]
        observed_seconds += observation["observed_seconds"]
        if not observation["has_carry_in"]:
            partial_history_faculty += 1

    total_faculty = len(faculty)
    possible_faculty_seconds = possible_window_seconds * total_faculty
    warning_flags = [
        "uses_current_roster_assumption",
        "no_historical_roster_membership",
        "no_college_operating_hours",
    ]
    if faculty_without_history:
        warning_flags.append("faculty_without_status_history")
    if partial_history_faculty:
        warning_flags.append("partial_status_history_without_carry_in")
    if window_end <= window_start:
        warning_flags.append("no_valid_observation_window")

    return {
        "calculable": observed_seconds > 0,
        "rate_percent": _percentage(available_seconds, observed_seconds),
        "available_seconds": round(available_seconds, 3),
        "observed_faculty_seconds": round(observed_seconds, 3),
        "faculty_with_history": faculty_with_history,
        "faculty_without_history": faculty_without_history,
        "partial_history_faculty": partial_history_faculty,
        "coverage_percent": _percentage(faculty_with_history, total_faculty),
        "observation_coverage_percent": _percentage(
            observed_seconds, possible_faculty_seconds
        ),
        "uses_current_roster_assumption": True,
        "operating_hours_available": False,
        "available_status_filter": ["available"],
        "warning_flags": warning_flags,
    }


def get_student_behavior(consultations):
    """Return period-bounded, non-identifying student aggregates."""

    counts = Counter(row.user_id for row in _consultation_rows(consultations))
    request_counts = [{'request_count': count} for count in counts.values()]
    unique_students = len(request_counts)
    repeat_students = sum(row["request_count"] > 1 for row in request_counts)
    total = sum(row["request_count"] for row in request_counts)
    return {
        "unique_students": unique_students,
        "repeat_students": repeat_students,
        "repeat_student_rate_percent": _percentage(
            repeat_students, unique_students
        ),
        "average_requests_per_student": (
            round(total / unique_students, 2) if unique_students else None
        ),
        "request_frequency_distribution": sorted(
            (row["request_count"] for row in request_counts), reverse=True
        ),
        "contains_personally_identifying_information": False,
    }


def get_student_request_frequency_display(consultations, limit=10):
    """Return identifying rows for the existing dashboard, never the AI payload."""

    rows = consultations.values(
        "user__first_name",
        "user__last_name",
        "user__username",
    ).annotate(request_count=Count("request_id")).order_by(
        "-request_count", "user__username"
    )[:limit]
    result = []
    for row in rows:
        full_name = f"{row['user__first_name']} {row['user__last_name']}".strip()
        result.append({
            "name": full_name or row["user__username"],
            "count": row["request_count"],
        })
    return result


def get_faculty_workload(consultations):
    """Return period-bounded workload counts without faculty names or emails."""

    by_faculty = defaultdict(Counter)
    for row in _consultation_rows(consultations):
        by_faculty[row.faculty_id][row.status] += 1
    rows = []
    for faculty_id, counts in by_faculty.items():
        row = {'faculty_id': faculty_id, 'total_requests': sum(counts.values())}
        row.update({f'{status}_requests': counts[status] for status, _ in ConsultationRequest.STATUS_CHOICES})
        rows.append(row)
    rows.sort(key=lambda row: (-row['total_requests'], row['faculty_id']))
    items = []
    for row in rows:
        items.append({
            "faculty_key": f"faculty:{row['faculty_id']}",
            "total_requests": row["total_requests"],
            "completed_requests": row["completed_requests"],
            "pending_requests": row["pending_requests"],
            "approved_requests": row["approved_requests"],
            "declined_requests": row["declined_requests"],
            "cancelled_requests": row["cancelled_requests"],
            "completion_rate_percent": _percentage(
                row["completed_requests"], row["total_requests"]
            ),
        })
    return {
        "period_bounded": True,
        "interpretation": "workload_not_employee_evaluation",
        "items": items,
    }


def _average_minutes(durations):
    if not durations:
        return None
    return round(
        sum(duration.total_seconds() for duration in durations)
        / len(durations)
        / 60,
        2,
    )


def get_walk_in_analytics(college_code, period):
    """Return college-scoped walk-in volume and explicitly labeled timing proxies."""

    walk_ins = WalkInQueue.objects.filter(
        faculty__college_id__iexact=college_code,
        joined_at__gte=period.start_datetime,
        joined_at__lt=period.end_datetime_exclusive,
    )
    distribution = {key: 0 for key in _status_keys(WalkInQueue.QUEUE_STATUS_CHOICES)}
    walk_ins = list(walk_ins.only('status', 'joined_at', 'notified_at', 'served_at'))
    distribution.update(Counter(row.status for row in walk_ins))

    hour_counts = Counter()
    weekday_counts = Counter()
    monthly_counts = Counter()
    join_to_notification = []
    join_to_completion = []
    notification_to_completion = []
    missing_notified_at = 0
    missing_served_at = 0

    for queue in walk_ins:
        local_joined_at = queue.joined_at.astimezone(period.timezone)
        hour_counts[local_joined_at.hour] += 1
        weekday_counts[local_joined_at.weekday()] += 1
        monthly_counts[local_joined_at.strftime("%Y-%m")] += 1
        if queue.notified_at is None:
            missing_notified_at += 1
        elif queue.notified_at >= queue.joined_at:
            join_to_notification.append(queue.notified_at - queue.joined_at)
        if queue.served_at is None:
            missing_served_at += 1
        elif queue.served_at >= queue.joined_at:
            join_to_completion.append(queue.served_at - queue.joined_at)
        if (
            queue.notified_at is not None
            and queue.served_at is not None
            and queue.served_at >= queue.notified_at
        ):
            notification_to_completion.append(queue.served_at - queue.notified_at)

    peak_hours, peak_hour_count = _peak(hour_counts)
    peak_weekdays, peak_weekday_count = _peak(weekday_counts)
    completed = distribution.get("completed", 0)
    resolved_denominator = completed + distribution.get("cancelled", 0)

    return {
        "timestamp_source": "joined_at",
        "timezone": period.timezone_name,
        "total": len(walk_ins),
        "status_distribution": distribution,
        "completed_count": completed,
        "resolved_denominator": resolved_denominator,
        "resolved_completion_rate_percent": _percentage(
            completed, resolved_denominator
        ),
        "hourly_distribution": [
            {"hour": hour, "count": hour_counts.get(hour, 0)}
            for hour in range(24)
        ],
        "peak_join_hour": {"hours": peak_hours, "count": peak_hour_count},
        "weekday_distribution": [
            {"weekday": name, "count": weekday_counts.get(index, 0)}
            for index, name in enumerate(WEEKDAY_NAMES)
        ],
        "peak_join_weekday": {
            "weekdays": [WEEKDAY_NAMES[index] for index in peak_weekdays],
            "count": peak_weekday_count,
        },
        "monthly_trend": [
            {"month": month, "count": monthly_counts[month]}
            for month in sorted(monthly_counts)
        ],
        "timing": {
            "timing_is_proxy": True,
            "notified_at_is_actual_service_start": False,
            "average_join_to_notification_minutes": _average_minutes(
                join_to_notification
            ),
            "join_to_notification_sample_size": len(join_to_notification),
            "average_join_to_completion_minutes": _average_minutes(
                join_to_completion
            ),
            "join_to_completion_sample_size": len(join_to_completion),
            "average_notification_to_completion_minutes": _average_minutes(
                notification_to_completion
            ),
            "notification_to_completion_sample_size": len(
                notification_to_completion
            ),
            "missing_notified_at_count": missing_notified_at,
            "missing_served_at_count": missing_served_at,
        },
    }


def get_trends(college_code, period, *, current_rows=None):
    """Compare equal-duration scheduled-date periods and return monthly counts."""

    current = current_rows if current_rows is not None else _consultation_rows(
        get_base_consultation_queryset(college_code, period)
    )
    previous_end = period.start_date - timedelta(days=1)
    previous_start = previous_end - timedelta(days=period.duration_days - 1)
    previous_period = normalize_period(
        previous_start,
        previous_end,
        period.timezone_name,
    )
    previous = get_base_consultation_queryset(college_code, previous_period)
    previous_counts = previous.aggregate(
        total=Count('request_id'), completed=Count('request_id', filter=Q(status='completed')),
    )
    current_count = len(current)
    previous_count = previous_counts['total']
    current_completed = sum(row.status == 'completed' for row in current)
    previous_completed = previous_counts['completed']
    monthly_counts = Counter(
        row.date.strftime("%Y-%m") for row in current
    )
    warnings = []
    if not period.is_complete:
        warnings.append("Current period is incomplete; growth is provisional.")
    return {
        "comparison_method": "equal_duration_immediately_preceding_period",
        "current_period_count": current_count,
        "previous_period_count": previous_count,
        "growth_percent": (
            round(((current_count - previous_count) / previous_count) * 100, 2)
            if previous_count
            else None
        ),
        "current_completed_count": current_completed,
        "previous_completed_count": previous_completed,
        "completed_growth_percent": (
            round(
                ((current_completed - previous_completed) / previous_completed)
                * 100,
                2,
            )
            if previous_completed
            else None
        ),
        "growth_comparable": period.is_complete,
        "comparison_period": {
            "start_date": previous_start.isoformat(),
            "end_date": previous_end.isoformat(),
            "duration_days": period.duration_days,
        },
        "scheduled_consultations_by_month": [
            {"month": month, "count": monthly_counts[month]}
            for month in sorted(monthly_counts)
        ],
        "warnings": warnings,
    }


def get_capacity_capability():
    """Describe why authoritative capacity metrics are not currently possible."""

    return {
        "authoritatively_calculable": False,
        "available_capacity": None,
        "supply_demand_gap": None,
        "utilization_percent": None,
        "reason_codes": [
            "no_explicit_availability_windows",
            "no_consultation_slot_model",
            "no_operating_hours",
            "no_maximum_consultation_capacity",
            "schedule_events_are_not_capacity_slots",
        ],
    }


def _confidence_level(sample_size, coverage_days, distinct_weeks, unique_students):
    dimensions = {
        "consultation_sample": 2 if sample_size >= 100 else 1 if sample_size >= 20 else 0,
        "historical_coverage": 2 if coverage_days >= 90 else 1 if coverage_days >= 28 else 0,
        "distinct_weeks": 2 if distinct_weeks >= 8 else 1 if distinct_weeks >= 3 else 0,
        "unique_students": 2 if unique_students >= 20 else 1 if unique_students >= 5 else 0,
    }
    labels = ("low", "moderate", "good")
    return labels[min(dimensions.values())], {
        key: labels[value] for key, value in dimensions.items()
    }


def get_data_quality(
    consultations,
    period,
    student_behavior,
    current_availability,
    historical_availability,
):
    """Return metric coverage and conservative multi-dimensional confidence."""

    consultations = _consultation_rows(consultations)
    sample_size = len(consultations)
    scheduled_dates = [row.date for row in consultations]
    distinct_weeks = len({value.isocalendar()[:2] for value in scheduled_dates})
    months_with_data = len({(value.year, value.month) for value in scheduled_dates})
    if scheduled_dates:
        historical_coverage_days = (max(scheduled_dates) - min(scheduled_dates)).days + 1
    else:
        historical_coverage_days = 0
    unique_students = student_behavior["unique_students"]
    confidence, confidence_dimensions = _confidence_level(
        sample_size,
        historical_coverage_days,
        distinct_weeks,
        unique_students,
    )
    missing_start_time = sum(row.start_time is None for row in consultations)
    missing_end_time = sum(row.end_time is None for row in consultations)
    missing_approved_at = sum(row.approved_at is None for row in consultations)
    response_time_sample_size = sample_size - missing_approved_at
    warnings = []
    if sample_size < 20:
        warnings.append("Low consultation sample size.")
    if historical_coverage_days < 28 or distinct_weeks < 3:
        warnings.append(
            "Historical coverage is insufficient for strong trend conclusions."
        )
    if unique_students < 5:
        warnings.append("Too few unique students are represented.")
    if response_time_sample_size < 5 or (
        sample_size and response_time_sample_size / sample_size < 0.5
    ):
        warnings.append("Response-time analysis has limited timestamp coverage.")
    if missing_start_time or missing_end_time:
        warnings.append("Some consultations are missing scheduled time fields.")
    availability_coverage = historical_availability["coverage_percent"]
    if availability_coverage is None or availability_coverage < 70:
        warnings.append("Faculty availability-history coverage is limited.")
    if not period.is_complete:
        warnings.append("Current period is incomplete.")

    return {
        "consultation_sample_size": sample_size,
        "distinct_weeks_represented": distinct_weeks,
        "months_with_data": months_with_data,
        "historical_coverage_days": historical_coverage_days,
        "unique_students": unique_students,
        "active_faculty": current_availability["total_active_faculty"],
        "missing_start_time_count": missing_start_time,
        "missing_end_time_count": missing_end_time,
        "missing_approved_at_count": missing_approved_at,
        "response_time_sample_size": response_time_sample_size,
        "faculty_availability_history_coverage_percent": availability_coverage,
        "confidence": confidence,
        "confidence_dimensions": confidence_dimensions,
        "warnings": warnings,
    }


def get_faculty_trends(
    college_code,
    start_date=None,
    end_date=None,
    timezone_name=DEFAULT_ANALYTICS_TIMEZONE,
    *, status_period=False,
):
    """Return centralized per-faculty trend data for the existing trends page."""

    period = normalize_period(start_date, end_date, timezone_name)
    status_window_end = min(period.end_datetime_exclusive, period.generated_at)
    status_window_start = period.start_datetime if status_period else status_window_end - timedelta(days=7)
    elapsed_days = max((status_window_end - status_window_start).total_seconds() / 86400, 0)
    history_for_faculty = StatusHistory.objects.filter(faculty_id=OuterRef('faculty_id'))
    faculty = list(_eligible_faculty(college_code).annotate(
        carry_status=Subquery(history_for_faculty.filter(
            changed_at__lt=status_window_start,
        ).order_by('-changed_at').values('status')[:1]),
        latest_change=Subquery((history_for_faculty.filter(changed_at__gte=status_window_start, changed_at__lt=status_window_end) if status_period else history_for_faculty).order_by('-changed_at').values('changed_at')[:1]),
    ).order_by('faculty_id'))
    faculty_ids = [profile.faculty_id for profile in faculty]
    consultations = get_base_consultation_queryset(college_code, period).filter(faculty_id__in=faculty_ids)
    counts = {
        row['faculty_id']: row
        for row in consultations.order_by().values('faculty_id').annotate(
            total=Count('request_id'),
            completed=Count('request_id', filter=Q(status='completed')),
        )
    }
    responses_by_faculty = defaultdict(list)
    # Approval activity belongs to the period in which approval was recorded,
    # independently of the appointment dates used by completion rates above.
    for faculty_id, requested_at, approved_at in get_base_consultation_queryset(college_code).filter(
        faculty_id__in=faculty_ids,
        approved_at__gte=period.start_datetime,
        approved_at__lt=period.end_datetime_exclusive,
    ).values_list('faculty_id', 'requested_at', 'approved_at'):
        duration_hours = (approved_at - requested_at).total_seconds() / 3600
        if duration_hours >= 0:
            responses_by_faculty[faculty_id].append(duration_hours)
    history_by_faculty = defaultdict(list)
    for row in StatusHistory.objects.filter(
        faculty_id__in=faculty_ids,
        changed_at__gte=status_window_start,
        changed_at__lt=status_window_end,
    ).only('faculty_id', 'status', 'changed_at').order_by('changed_at'):
        history_by_faculty[row.faculty_id].append(row)
    items = []
    for profile in faculty:
        totals = counts.get(profile.faculty_id, {})
        total_requests = totals.get('total', 0)
        completed_requests = totals.get('completed', 0)
        rows = history_by_faculty[profile.faculty_id]
        status_update_count = len(rows)
        response_hours = responses_by_faculty[profile.faculty_id]
        observation = _integrate_status_history(
            profile.carry_status, rows, status_window_start, status_window_end,
        )
        items.append({
            "faculty_key": f"faculty:{profile.faculty_id}",
            "status_updates_last_7_days": status_update_count,
            "updates_per_day": round(status_update_count / elapsed_days, 1) if elapsed_days else 0,
            "last_update_at": (
                profile.latest_change.isoformat() if profile.latest_change else None
            ),
            "completion_rate_percent": _percentage(
                completed_requests, total_requests
            ),
            "average_approval_response_hours": (
                round(sum(response_hours) / len(response_hours), 1)
                if response_hours
                else None
            ),
            "availability_rate_percent": (
                _percentage(
                    observation["available_seconds"],
                    observation["observed_seconds"],
                )
                if observation
                else None
            ),
        })
    return {
        "consultation_period": {
            "start_date": period.start_date.isoformat(),
            "end_date": period.end_date.isoformat(),
        },
        "status_window_days": 7,
        "items": items,
    }


def get_college_analytics(
    college_code,
    start_date=None,
    end_date=None,
    timezone_name=DEFAULT_ANALYTICS_TIMEZONE,
):
    """Return the canonical JSON-safe analytics payload for one college."""

    period = normalize_period(start_date, end_date, timezone_name)
    normalized_college_code = str(college_code or "").strip()
    consultations = _consultation_rows(get_base_consultation_queryset(
        normalized_college_code, period
    ))
    summary = get_consultation_summary(consultations)
    consultation_patterns = get_scheduled_consultation_patterns(consultations)
    request_patterns = get_request_submission_patterns(
        normalized_college_code, period
    )
    availability_snapshot = _availability_history(normalized_college_code, period)
    current_availability = get_current_availability(
        normalized_college_code, faculty=availability_snapshot[0],
    )
    historical_availability = get_historical_availability_proxy(
        normalized_college_code, period, snapshot=availability_snapshot,
    )
    student_behavior = get_student_behavior(consultations)
    faculty_workload = get_faculty_workload(consultations)
    walk_ins = get_walk_in_analytics(normalized_college_code, period)
    trends = get_trends(normalized_college_code, period, current_rows=consultations)
    data_quality = get_data_quality(
        consultations,
        period,
        student_behavior,
        current_availability,
        historical_availability,
    )
    college = College.objects.filter(code__iexact=normalized_college_code).first()

    return {
        "schema_version": "1.0",
        "scope": {
            "college_code": normalized_college_code,
            "college_name": college.name if college else None,
            "timezone": period.timezone_name,
        },
        "period": period.as_dict(),
        "consultations": summary,
        "consultation_patterns": consultation_patterns,
        "request_patterns": request_patterns,
        "faculty_availability": {
            "current": current_availability,
            "historical_proxy": historical_availability,
        },
        "student_behavior": student_behavior,
        "faculty_workload": faculty_workload,
        "walk_ins": walk_ins,
        "trends": trends,
        "capacity": get_capacity_capability(),
        "data_quality": data_quality,
    }
