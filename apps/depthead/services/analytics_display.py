"""Shared presentation for analytics pages and the preset browser."""
from datetime import date, timedelta
from django.utils.dateparse import parse_datetime
from django.utils.timesince import timesince
from apps.faculty.models import FacultyProfile
from .analytics import normalize_period


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
