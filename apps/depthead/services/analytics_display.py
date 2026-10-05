"""Shared presentation for analytics pages and the preset browser."""
from datetime import date, timedelta
from django.utils.dateparse import parse_datetime
from django.utils.timesince import timesince
from apps.faculty.models import FacultyProfile, ConsultationRequest
from .analytics import normalize_period
from .schedule_availability import MIN_FREE_MINUTES, SCHEDULE_COUNT_NOTE


def student_reporting_period():
    current_period = normalize_period()
    today = current_period.end_date
    month_starts = []
    cursor = today.replace(day=1)
    for _ in range(6):
        month_starts.append(cursor)
        cursor = (cursor - timedelta(days=1)).replace(day=1)
    month_starts.reverse()  #oldest to newest

    return month_starts, today


def consultation_topics_display(summary):
    """Present the existing agenda counts without fetching consultation rows."""
    total = summary['total_records']
    if not total:
        return []
    labels = dict(ConsultationRequest.AGENDA_CHOICES)
    counts = dict.fromkeys(labels, 0)
    for key, count in summary['agenda_distribution'].items():
        bucket = key if key and key.strip() else None
        counts[bucket] = counts.get(bucket, 0) + count
    rows = [
        {
            'label': labels.get(key, f'Unrecognized topic ({key})') if key else 'Unspecified',
            'count': count,
            'percentage': round(count / total * 100, 2),
        }
        for key, count in counts.items()
        if key in labels or count
    ]
    return sorted(rows, key=lambda row: (-row['count'], row['label']))


def peak_request_month(request_months):
    if request_months:
        peak_period_count = max(row['count'] for row in request_months)
        peak_months = [
            date.fromisoformat(f"{row['month']}-01").strftime('%B %Y')
            for row in request_months
            if row['count'] == peak_period_count
        ]
        peak_period_label = ', '.join(peak_months)
    else:
        peak_period_label = "No data"
        peak_period_count = 0

    return peak_period_label, peak_period_count


def faculty_load_display(analytics):
    # Names are presentation-only and are not present in the AI-ready payload.
    workload_items = analytics['faculty_workload']['items'][:5]
    faculty_ids = [item['faculty_key'].removeprefix('faculty:') for item in workload_items]
    profiles_by_id = {
        profile.faculty_id: profile
        for profile in FacultyProfile.objects.filter(
            faculty_id__in=faculty_ids
        ).select_related('user')
    }
    load_distribution_list = []
    for item in workload_items:
        faculty_id = item['faculty_key'].removeprefix('faculty:')
        profile = profiles_by_id.get(faculty_id)
        if profile is None:
            continue
        load_distribution_list.append({
            'name': profile.user.get_full_name() or profile.user.username,
            'count': item['total_requests'],
        })

    return load_distribution_list


def faculty_trends_display(analytics):
    faculty_ids = [
        item['faculty_key'].removeprefix('faculty:')
        for item in analytics['items']
    ]
    profiles_by_id = {
        profile.faculty_id: profile
        for profile in FacultyProfile.objects.filter(
            faculty_id__in=faculty_ids
        ).select_related('user')
    }
    trends = []
    for item in analytics['items']:
        faculty_id = item['faculty_key'].removeprefix('faculty:')
        profile = profiles_by_id.get(faculty_id)
        if profile is None:
            continue
        last_update_at = parse_datetime(item['last_update_at']) if item['last_update_at'] else None
        trends.append({
            'name': profile.user.get_full_name() or profile.user.username,
            'updates_per_day': item['updates_per_day'],
            'last_update_display': f"{timesince(last_update_at)} ago" if last_update_at else "No data",
            'completion_rate': item['completion_rate_percent'],
            'avg_response_hours': item['average_approval_response_hours'],
            'availability_rate': item['availability_rate_percent'],
        })


    return trends


def most_available_faculty_recommendation(schedule_availability):
    """Format the local schedule ranking for the Dept Head recommendations."""

    rows = schedule_availability.get('rows', [])
    ranked_rows = [row for row in rows if row.get('winners')]
    if not ranked_rows:
        return None

    daily_results = []
    for row in ranked_rows:
        day = row['date']
        names = ', '.join(row['winners'])
        daily_results.append(
            f"{row['day']} ({day.strftime('%b')} {day.day}): {names}"
        )

    return {
        'title': 'Most available faculty member per day',
        'description': (
            f"Based on recorded schedules for {schedule_availability['week_start'].strftime('%b')} "
            f"{schedule_availability['week_start'].day}–{schedule_availability['week_end'].strftime('%b')} "
            f"{schedule_availability['week_end'].day}, the daily ranking is: "
            f"{'; '.join(daily_results)}."
        ),
    }


def schedule_availability_ai_summary(schedule_availability):
    """Return anonymous schedule aggregates that are safe to send to Gemini."""

    return {
        'week_start': schedule_availability['week_start'].isoformat(),
        'week_end': schedule_availability['week_end'].isoformat(),
        'faculty_count': schedule_availability['faculty_count'],
        'minimum_free_minutes': MIN_FREE_MINUTES,
        'working_hours': '8 AM–5 PM',
        'interpretation': SCHEDULE_COUNT_NOTE,
        'daily': [
            {
                'day': row['day'],
                'date': row['date'].isoformat(),
                'available_count': row['available_count'],
                'faculty_count': schedule_availability['faculty_count'],
                'availability_percent': row['availability_percent'],
            }
            for row in schedule_availability.get('rows', [])
        ],
    }


def most_available_days_recommendation(schedule_availability):
    """Recommend the current week's days with the highest faculty availability."""

    rows = [
        row for row in schedule_availability.get('rows', [])
        if row.get('availability_percent') is not None
    ]
    if not rows or not schedule_availability.get('faculty_count'):
        return None

    highest_rate = max(row['availability_percent'] for row in rows)
    best_days = [row for row in rows if row['availability_percent'] == highest_rate]
    day_text = ', '.join(
        f"{row['day']} ({row['date'].strftime('%b')} {row['date'].day})"
        for row in best_days
    )
    return {
        'title': 'Best days for department events or retreats',
        'description': (
            f"{day_text} have the highest share of faculty with at least two consecutive hours of open schedule time this week "
            f"({highest_rate}% or {best_days[0]['available_count']} of "
            f"{schedule_availability['faculty_count']} faculty). These are schedule-based planning estimates, "
            "not confirmed availability. Faculty without recorded schedules count as fully unscheduled."
        ),
    }
