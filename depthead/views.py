import csv

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from core.decorators import role_required
from core.models import User, FacultyInvite, OfficeClosure, CollegeAnnouncement, College
from core.forms import CollegeAnnouncementForm, CollegeDescriptionForm
from django.contrib import messages
from .forms import FacultyInviteForm, OfficeClosureForm
from faculty.models import FacultyProfile, ScheduleEvent
from faculty.views import SCHEDULE_CSV_HEADERS, _event_json, _parse_schedule_csv, _schedule_csv_row
from django.utils import timezone
from django.http import HttpResponse, JsonResponse
from django.db import transaction
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_POST
from django.views.decorators.http import require_GET
from core.services import notify_college_users, send_faculty_invite_email, send_faculty_approved_email, send_faculty_removed_email
from core.faculty import mark_inactive_faculty
from datetime import timedelta, date
from django.utils.dateparse import parse_datetime
from django.utils.timesince import timesince
from .services import (
    generate_ai_insights,
    get_college_analytics,
    get_stored_ai_insights,
)
from .services.analytics import (
    get_base_consultation_queryset,
    get_faculty_trends,
    get_student_request_frequency_display,
    normalize_period,
)


@login_required
@role_required('depthead')
def approve_faculty(request, user_id):
    faculty_user = get_object_or_404(User, id=user_id, role='faculty', account_status='pending', college__iexact=request.user.college)
    if request.method == 'POST':
        faculty_user.account_status = 'active'
        faculty_user.save()
        send_faculty_approved_email(faculty_user)
        return JsonResponse({'success': True, 'message': f"{faculty_user.get_full_name() or faculty_user.username} approved."})
    return JsonResponse({'success': False, 'error': 'Invalid request method.'}, status=405)


@login_required
@role_required('depthead')
def decline_faculty(request, user_id):
    faculty_user = get_object_or_404(User, id=user_id, role='faculty', account_status='pending', college__iexact=request.user.college)
    if request.method == 'POST':
        faculty_user.account_status = 'declined'
        faculty_user.save()
        return JsonResponse({'success': True, 'message': f"{faculty_user.get_full_name() or faculty_user.username} declined."})
    return JsonResponse({'success': False, 'error': 'Invalid request method.'}, status=405)


@login_required
@role_required('depthead')
def invite_faculty(request):
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    if request.method == 'POST':
        if not request.user.college:
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'error': 'Your account has no college set. Contact a Super Admin.',
                }, status=400)
            messages.error(request, "Your account has no college set. Contact a Super Admin.")
            return redirect('depthead:admin_faculty')
        requested_email = request.POST.get('email', '').strip()
        used_invite = FacultyInvite.objects.filter(
            email__iexact=requested_email,
            used=True,
        ).first()
        form = FacultyInviteForm(request.POST, instance=used_invite)
        if form.is_valid():
            invite = form.save(commit=False)
            invite.college = request.user.college
            invite.invited_by = request.user
            invite.used = False
            invite.save()
            send_faculty_invite_email(invite.email, invite.college)
            if is_ajax:
                return JsonResponse({
                    'success': True,
                    'message': f"Invitation created for {invite.email}.",
                }, status=201)
            messages.success(request, f"Invitation created for {invite.email}.")
        else:
            if is_ajax:
                errors = ' '.join(
                    error for error_list in form.errors.values() for error in error_list
                )
                return JsonResponse({
                    'success': False,
                    'error': errors or 'Unable to create the faculty invitation.',
                }, status=400)
            for error_list in form.errors.values():
                for error in error_list:
                    messages.error(request, error)
    return redirect('depthead:admin_faculty')


@login_required
@role_required('depthead')
def remove_faculty(request, user_id):
    faculty_user = get_object_or_404(User, id=user_id, role='faculty', account_status='active', college__iexact=request.user.college)
    if request.method == 'POST':
        name = faculty_user.get_full_name() or faculty_user.username
        email = faculty_user.email
        faculty_user.delete()
        send_faculty_removed_email(email, name)
        return JsonResponse({'success': True, 'message': f"{name} removed."})
    return JsonResponse({'success': False, 'error': 'Invalid request method.'}, status=405)


@login_required
@role_required('depthead')
def admin_dashboard(request):
    college_code = request.user.college
    college = College.objects.filter(code__iexact=college_code).first()
    analytics = get_college_analytics(college_code)
    summary = analytics['consultations']
    trends = analytics['trends']
    availability = analytics['faculty_availability']['current']
    growth_comparable = trends['growth_comparable']

    return render(request, 'depthead/adminDashboard.html', {
        'college': college,
        'total_this_month': summary['total_records'],
        'total_change_pct': trends['growth_percent'] if growth_comparable else None,
        'completed_this_month': summary['completion']['completed_count'],
        'completed_change_pct': trends['completed_growth_percent'] if growth_comparable else None,
        'active_faculty_count': availability['total_active_faculty'],
        'available_now_count': availability['available_count'],
        'available_now_pct': availability['availability_rate_percent'],
        'analysis_period': analytics['period'],
        'data_quality': analytics['data_quality'],
        'analytics': analytics,
        'ai_insights': {'available': None},
    })


@login_required
@role_required('depthead')
@require_GET
def ai_insights_api(request):
    """Return AI interpretation for the authenticated College Head's scope."""

    stored_insights = get_stored_ai_insights(request.user.college)
    if stored_insights is not None:
        return JsonResponse(stored_insights)

    analytics = get_college_analytics(request.user.college)
    return JsonResponse(generate_ai_insights(analytics))


@login_required
@role_required('depthead')
def admin_faculty(request):
    faculty_users = list(User.objects.filter(
        role='faculty',
        college__iexact=request.user.college,
    ).select_related('faculty_profile').order_by('first_name', 'last_name', 'username'))

    mark_inactive_faculty(faculty_users)

    return render(request, 'depthead/adminFaculty.html', {
        'pending_faculty': [u for u in faculty_users if u.account_status == 'pending'],
        'active_faculty': [u for u in faculty_users if u.account_status == 'active'],
    })


@login_required
@role_required('depthead')
def faculty_schedule_template(request):
    """Download the CSV format used for college-head faculty uploads."""
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename=schedule_template.csv'
    writer = csv.writer(response)
    writer.writerow(SCHEDULE_CSV_HEADERS)
    writer.writerow([
        'Introductory lecture', 'Introductory lecture', 'Room 204',
        'Monday', '8', '5', '10:30', '12:00', 'Busy',
    ])
    writer.writerow([
        'Office hours', 'Student consultations', 'Room 204',
        'Monday', '8', '5', '13:00', '15:00', 'Busy',
    ])
    return response


@login_required
@role_required('depthead')
@csrf_protect
def upload_faculty_schedule(request, faculty_id):
    """Append a validated CSV schedule to a selected faculty member in this college."""
    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST requests are allowed.'}, status=405)
    faculty = get_object_or_404(
        FacultyProfile.objects.select_related('user'),
        faculty_id=faculty_id,
        college_id__iexact=request.user.college,
        user__role='faculty',
    )
    try:
        rows = _parse_schedule_csv(request.FILES.get('file'))
    except ValueError as exc:
        detail = exc.args[0] if exc.args else 'Invalid CSV file.'
        errors = detail if isinstance(detail, list) else [detail]
        return JsonResponse({'error': 'The schedule was not saved.', 'errors': errors}, status=400)

    updated_at = timezone.now()
    with transaction.atomic():
        events = ScheduleEvent.objects.bulk_create([
            ScheduleEvent(
                faculty=faculty,
                title=row['title'],
                description=row['description'],
                location=row['room'],
                schedule_status=row['status'],
                event_type=row['event_type'],
                date=None,
                day_of_week=row['day_of_week'],
                start_month=row['start_month'],
                end_month=row['end_month'],
                start_time=row['start_time'],
                end_time=row['end_time'],
                managed_by_facsync=True,
                sync_state='local',
            )
            for row in rows
        ])
        faculty.schedule_last_updated_at = updated_at
        faculty.save(update_fields=['schedule_last_updated_at'])

    return JsonResponse({
        'message': f'Schedule uploaded for {faculty.user.get_full_name() or faculty.user.username}. {len(events)} row(s) added.',
        'added_count': len(events),
        'last_updated_at': updated_at.isoformat(),
        'preview': [_schedule_csv_row(event) for event in events],
        'events': [_event_json(event) for event in events],
    }, status=201)


@login_required
@role_required('depthead')
def view_faculty_schedule_preview(request, faculty_id):
    """Return the uploaded FacSync schedule rows for a faculty member."""
    faculty = get_object_or_404(
        FacultyProfile.objects.select_related('user'),
        faculty_id=faculty_id,
        college_id__iexact=request.user.college,
        user__role='faculty',
    )
    events = list(
        ScheduleEvent.objects.filter(
            faculty=faculty,
            managed_by_facsync=True,
        ).order_by('id')
    )
    return JsonResponse({
        'faculty_id': faculty.faculty_id,
        'faculty_name': faculty.user.get_full_name() or faculty.user.username,
        'last_updated_at': faculty.schedule_last_updated_at.isoformat() if faculty.schedule_last_updated_at else None,
        'preview': [_schedule_csv_row(event) for event in events],
        'events': [_event_json(event) for event in events],
    })


@login_required
@role_required('depthead')
@csrf_protect
def delete_faculty_schedule(request, faculty_id):
    """Delete only FacSync-managed uploaded schedule rows for one faculty member."""
    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST requests are allowed.'}, status=405)
    faculty = get_object_or_404(
        FacultyProfile.objects.select_related('user'),
        faculty_id=faculty_id,
        college_id__iexact=request.user.college,
        user__role='faculty',
    )
    with transaction.atomic():
        deleted_count, _ = ScheduleEvent.objects.filter(
            faculty=faculty,
            managed_by_facsync=True,
        ).delete()
        faculty.schedule_last_updated_at = None
        faculty.save(update_fields=['schedule_last_updated_at'])
    return JsonResponse({
        'success': True,
        'message': f'Uploaded schedule deleted for {faculty.user.get_full_name() or faculty.user.username}.',
        'deleted_count': deleted_count,
    })


@login_required
@role_required('depthead')
def student_behavior(request):
    college_code = request.user.college
    current_period = normalize_period()
    today = current_period.end_date
    month_starts = []
    cursor = today.replace(day=1)
    for _ in range(6):
        month_starts.append(cursor)
        cursor = (cursor - timedelta(days=1)).replace(day=1)
    month_starts.reverse()  #oldest to newest

    analytics = get_college_analytics(college_code, month_starts[0], today)
    monthly_lookup = {
        row['month']: row['count']
        for row in analytics['trends']['scheduled_consultations_by_month']
    }

    monthly_data = []
    for m_start in month_starts:
        monthly_data.append({
            'month': m_start,
            'label': m_start.strftime('%b'),
            'count': monthly_lookup.get(m_start.strftime('%Y-%m'), 0),
        })

    max_month_count = max((m['count'] for m in monthly_data), default=0) or 1
    chart_width = 460
    chart_left = 50
    chart_bottom = 160
    chart_top = 40
    step = chart_width / (len(monthly_data) - 1) if len(monthly_data) > 1 else 0

    line_points = []
    for i, m in enumerate(monthly_data):
        x = chart_left + i * step
        y = chart_bottom - round((m['count'] / max_month_count) * (chart_bottom - chart_top))
        line_points.append({'x': round(x, 1), 'y': y, 'label': m['label'], 'count': m['count']})

    polyline_str = " ".join(f"{p['x']},{p['y']}" for p in line_points)

    # Request-submission periods use requested_at in the analytics timezone.
    request_months = analytics['request_patterns']['monthly_trend']
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

    consultations_qs = get_base_consultation_queryset(
        college_code,
        normalize_period(month_starts[0], today),
    )
    student_frequency = get_student_request_frequency_display(consultations_qs)

    return render(request, 'depthead/studentBehavior.html', {
        'line_points': line_points,
        'polyline_str': polyline_str,
        'peak_period_label': peak_period_label,
        'peak_period_count': peak_period_count,
        'student_frequency': student_frequency,
    })


STATUS_LABELS = {
    'available': ('Available', 'status-available'),
    'busy': ('Busy', 'status-busy'),
    'virtual_only': ('Virtual Only', 'status-virtual'),
    'on_leave': ('On Leave', 'status-on-leave'),
    'unavailable': ('Unavailable', 'status-unavailable'),
}


@login_required
@role_required('depthead')
def faculty_monitoring(request):
    inactivity_threshold = timezone.now() - timedelta(days=30)
    profiles = FacultyProfile.objects.select_related('user').filter(
        user__role='faculty',
        user__account_status='active',
        college_id__iexact=request.user.college,
    )
    faculty_list = []
    for profile in profiles:
        label, css_class = STATUS_LABELS.get(profile.current_status, ('Unknown', 'status-unavailable'))
        last_login = profile.user.last_login
        is_inactive = last_login is None or last_login < inactivity_threshold
        faculty_list.append({
            'name': profile.user.get_full_name() or profile.user.username,
            'status_label': label,
            'status_class': css_class,
            'updated_at': profile.status_updated_at,
            'is_inactive': is_inactive,
            'last_login': last_login,
        })
    return render(request, 'depthead/facultyMonitoring.html', {'faculty_list': faculty_list})


@login_required
@role_required('depthead')
def college_settings(request):
    closure, _ = OfficeClosure.objects.get_or_create(
        college__iexact=request.user.college,
        defaults={'college': request.user.college}
    )
    if request.method == 'POST':
        form = OfficeClosureForm(request.POST, instance=closure)
        if form.is_valid():
            closure = form.save(commit=False)
            closure.college = request.user.college
            closure.updated_by = request.user
            closure.save()
            return JsonResponse({'success': True})
        errors = ' '.join(
            error for error_list in form.errors.values() for error in error_list
        )
        return JsonResponse({'success': False, 'error': errors or 'Unable to save closure settings.'})
    else:
        form = OfficeClosureForm(instance=closure)

    college_announcements = CollegeAnnouncement.objects.filter(
        college__iexact=request.user.college,
        expiry__gt=timezone.now()
    )

    college = College.objects.filter(code__iexact=request.user.college).first()

    return render(request, 'depthead/collegeSettings.html', {
        'closure_form': form,
        'college_announcements': college_announcements,
        'college': college,
    })


WEEKDAY_LABELS = {
    1: 'Sunday', 2: 'Monday', 3: 'Tuesday', 4: 'Wednesday',
    5: 'Thursday', 6: 'Friday', 7: 'Saturday',
}  # Django's ExtractWeekDay: 1=Sunday ... 7=Saturday


@login_required
@role_required('depthead')
def peak_analytics(request):
    college_code = request.user.college
    analytics = get_college_analytics(college_code)
    patterns = analytics['consultation_patterns']
    hourly_data = {
        row['hour']: row['count'] for row in patterns['hourly_distribution']
    }
    peak_hours = patterns['peak_hour']['hours']
    peak_hour_label = ', '.join(
        f"{hour % 12 or 12}{'AM' if hour < 12 else 'PM'}" for hour in peak_hours
    ) or 'No data'
    peak_hour_count = patterns['peak_hour']['count']
    weekday_rows = patterns['weekday_distribution']
    weekday_totals = {row['weekday']: row['count'] for row in weekday_rows}
    peak_day_label = ', '.join(patterns['peak_weekday']['weekdays']) or 'No data'
    peak_day_count = patterns['peak_weekday']['count']

    # Build pie chart slices
    total_weekday_requests = sum(weekday_totals.values())
    pie_colors = ['#2563eb', '#3b82f6', '#60a5fa', '#93c5fd', '#1d4ed8', '#1e40af', '#bfdbfe']
    pie_slices = []
    if total_weekday_requests > 0:
        cx, cy, r = 110, 110, 90
        start_angle = -90  # start at top
        for i, weekday_name in enumerate(WEEKDAY_LABELS.values()):
            count = weekday_totals.get(weekday_name, 0)
            if count == 0:
                continue
            fraction = count / total_weekday_requests
            sweep_angle = fraction * 360
            end_angle = start_angle + sweep_angle

            import math
            start_rad = math.radians(start_angle)
            end_rad = math.radians(end_angle)
            x1 = cx + r * math.cos(start_rad)
            y1 = cy + r * math.sin(start_rad)
            x2 = cx + r * math.cos(end_rad)
            y2 = cy + r * math.sin(end_rad)
            large_arc = 1 if sweep_angle > 180 else 0

            path = f"M {cx},{cy} L {x1:.2f},{y1:.2f} A {r},{r} 0 {large_arc} 1 {x2:.2f},{y2:.2f} Z"
            pie_slices.append({
                'path': path,
                'color': pie_colors[i % len(pie_colors)],
                'label': weekday_name,
                'count': count,
                'pct': round(fraction * 100),
            })
            start_angle = end_angle

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

    max_count = max(hourly_data.values()) if any(hourly_data.values()) else 1
    chart_bars = []
    gap = 20
    start_x = 42
    max_bar_height = 110
    baseline_y = 160

    for i, (hour, count) in enumerate(hourly_data.items()):
        bar_height = round((count / max_count) * max_bar_height) if max_count else 0
        chart_bars.append({
            'x': start_x + i * gap,
            'y': baseline_y - bar_height,
            'height': bar_height,
            'label': f"{hour % 12 or 12}{'AM' if hour < 12 else 'PM'}",
            'count': count,
        })

    return render(request, 'depthead/peakAnalytics.html', {
        'hourly_data': hourly_data,
        'chart_bars': chart_bars,
        'peak_hour_label': peak_hour_label,
        'peak_hour_count': peak_hour_count,
        'peak_day_label': peak_day_label,
        'peak_day_count': peak_day_count,
        'pie_slices': pie_slices, 
        'capacity': analytics['capacity'],
        'load_distribution': load_distribution_list,
        'analysis_period': analytics['period'],
    })

@login_required
@role_required('depthead')
def faculty_trends(request):
    college_code = request.user.college
    analytics = get_faculty_trends(college_code)
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

    
    #chart bars, one per faculty
    max_bar_height = 160
    baseline_y = 250
    bar_width = 40
    gap = 70
    start_x = 100
    chart_bars = []
    for i, t in enumerate(trends):
        rate = t['availability_rate']
        height = round((rate / 100) * max_bar_height) if rate is not None else 0
        chart_bars.append({
            'x': start_x + i * gap,
            'y': baseline_y - height,
            'height': height,
            'label': t['name'].split()[0] if t['name'] else '',
            'rate': rate,
            'has_data': rate is not None,
        })

    return render(request, 'depthead/facultyTrends.html', {
        'trends': trends,
        'chart_bars': chart_bars,
    })


@login_required
@role_required('depthead')
@require_POST
def create_announcement(request):
    if not request.user.college:
        return JsonResponse(
            {'success': False, 'error': "Your account has no college set. Contact a Super Admin."},
            status=400
        )

    form = CollegeAnnouncementForm(request.POST)
    if not form.is_valid():
        errors = [e for error_list in form.errors.values() for e in error_list]
        return JsonResponse({'success': False, 'error': ' '.join(errors)}, status=400)

    announcement = form.save(commit=False)
    announcement.college = request.user.college
    announcement.posted_by = request.user
    announcement.save()
    notify_college_users(
        college=announcement.college,
        notification_type='announcement',
        title='College announcement',
        message=announcement.message,
        url='',
        exclude_user_id=request.user.id,
    )

    return JsonResponse({
        'success': True,
        'announcement': {
            'message': announcement.message,
            'posted_at': announcement.posted_at.strftime('%b %d, %Y'),
            'expiry': announcement.expiry.strftime('%b %d, %Y'),
        }
    })


@login_required
@role_required('depthead')
def edit_college_description(request):
    college = College.objects.filter(code__iexact=request.user.college).first()
    if not college:
        messages.error(request, "Your college could not be found. Contact a Super Admin.")
        return redirect('depthead:college_settings')

    if request.method == 'POST':
        form = CollegeDescriptionForm(request.POST, instance=college)
        if form.is_valid():
            form.save()
            messages.success(request, "College description updated.")
        else:
            for error_list in form.errors.values():
                for error in error_list:
                    messages.error(request, error)

    return redirect('depthead:college_settings')

@login_required
@role_required('depthead')
def faculty_monitoring_data(request):
    inactivity_threshold = timezone.now() - timedelta(days=30)
    profiles = FacultyProfile.objects.select_related('user').filter(
        user__role='faculty',
        user__account_status='active',
        college_id__iexact=request.user.college,
    )
    faculty_list = []
    for profile in profiles:
        label, css_class = STATUS_LABELS.get(profile.current_status, ('Unknown', 'status-unavailable'))
        last_login = profile.user.last_login
        is_inactive = last_login is None or last_login < inactivity_threshold
        faculty_list.append({
            'id': profile.faculty_id,
            'name': profile.user.get_full_name() or profile.user.username,
            'status_label': label,
            'status_class': css_class,
            'updated_at_iso': profile.status_updated_at.isoformat() if profile.status_updated_at else None,
            'is_inactive': is_inactive,
        })
    return JsonResponse({'faculty_list': faculty_list})
