"""Frozen pre-batching implementation used only as a regression oracle."""
from datetime import timedelta
from apps.depthead.services.analytics import normalize_period, _eligible_faculty, get_base_consultation_queryset, _percentage, DEFAULT_ANALYTICS_TIMEZONE
from apps.faculty.models import StatusHistory

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
    if not carry_in and not rows:
        return None

    timeline = []
    if carry_in:
        timeline.append((window_start, carry_in.status))
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
        "has_carry_in": carry_in is not None,
    }


def get_faculty_trends(
    college_code,
    start_date=None,
    end_date=None,
    timezone_name=DEFAULT_ANALYTICS_TIMEZONE,
):
    """Return centralized per-faculty trend data for the existing trends page."""

    period = normalize_period(start_date, end_date, timezone_name)
    faculty = list(_eligible_faculty(college_code).order_by("faculty_id"))
    consultations = get_base_consultation_queryset(college_code, period)
    status_window_end = min(period.end_datetime_exclusive, period.generated_at)
    status_window_start = status_window_end - timedelta(days=7)
    items = []
    for profile in faculty:
        faculty_requests = consultations.filter(faculty=profile)
        total_requests = faculty_requests.count()
        completed_requests = faculty_requests.filter(status="completed").count()
        status_update_count = StatusHistory.objects.filter(
            faculty=profile,
            changed_at__gte=status_window_start,
            changed_at__lt=status_window_end,
        ).count()
        response_hours = []
        for requested_at, approved_at in faculty_requests.filter(
            approved_at__isnull=False
        ).values_list("requested_at", "approved_at"):
            duration_hours = (approved_at - requested_at).total_seconds() / 3600
            if duration_hours >= 0:
                response_hours.append(duration_hours)
        observation = _status_observation(
            profile, status_window_start, status_window_end
        )
        last_update = StatusHistory.objects.filter(
            faculty=profile
        ).order_by("-changed_at").first()
        items.append({
            "faculty_key": f"faculty:{profile.faculty_id}",
            "status_updates_last_7_days": status_update_count,
            "updates_per_day": round(status_update_count / 7, 1),
            "last_update_at": (
                last_update.changed_at.isoformat() if last_update else None
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
