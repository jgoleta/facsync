import csv

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from core.decorators import role_required
from core.models import User, FacultyInvite, OfficeClosure, DepartmentAnnouncement, Department
from core.forms import DepartmentAnnouncementForm, DepartmentDescriptionForm
from django.contrib import messages
from .forms import FacultyInviteForm, OfficeClosureForm
from faculty.models import FacultyProfile, ConsultationRequest, ScheduleEvent, StatusHistory
from faculty.views import SCHEDULE_CSV_HEADERS, _event_json, _parse_schedule_csv, _schedule_csv_row
from django.utils import timezone
from django.http import HttpResponse, JsonResponse
from django.db import transaction
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_POST
from core.services import notify_department_users
from django.db.models import Count, Avg, F, ExpressionWrapper, DurationField
from django.db.models.functions import ExtractHour, ExtractWeekDay, TruncMonth
from datetime import timedelta, date
from django.utils.timesince import timesince


@login_required
@role_required('depthead')
def pending_faculty_requests(request):
    pending_faculty = User.objects.filter(role='faculty', account_status='pending', department__iexact=request.user.department)
    active_faculty = User.objects.filter(role='faculty', account_status='active', department__iexact=request.user.department)
    return render(request, 'depthead/pendingFacultyRequests.html', {
        'pending_faculty': pending_faculty,
        'active_faculty': active_faculty,
    })


@login_required
@role_required('depthead')
def approve_faculty(request, user_id):
    faculty_user = get_object_or_404(User, id=user_id, role='faculty', account_status='pending', department__iexact=request.user.department)
    if request.method == 'POST':
        faculty_user.account_status = 'active'
        faculty_user.save()
        return JsonResponse({'success': True, 'message': f"{faculty_user.get_full_name() or faculty_user.username} approved."})
    return JsonResponse({'success': False, 'error': 'Invalid request method.'}, status=405)


@login_required
@role_required('depthead')
def decline_faculty(request, user_id):
    faculty_user = get_object_or_404(User, id=user_id, role='faculty', account_status='pending', department__iexact=request.user.department)
    if request.method == 'POST':
        faculty_user.account_status = 'declined'
        faculty_user.save()
        return JsonResponse({'success': True, 'message': f"{faculty_user.get_full_name() or faculty_user.username} declined."})
    return JsonResponse({'success': False, 'error': 'Invalid request method.'}, status=405)


@login_required
@role_required('depthead')
def invite_faculty(request):
    if request.method == 'POST':
        if not request.user.department:
            messages.error(request, "Your account has no department set. Contact a Super Admin.")
            return redirect('depthead:admin_faculty')
        form = FacultyInviteForm(request.POST)
        if form.is_valid():
            invite = form.save(commit=False)
            invite.department = request.user.department
            invite.invited_by = request.user
            invite.save()
            messages.success(request, f"Invitation created for {invite.email}.")
        else:
            for error_list in form.errors.values():
                for error in error_list:
                    messages.error(request, error)
    return redirect('depthead:admin_faculty')


@login_required
@role_required('depthead')
def remove_faculty(request, user_id):
    faculty_user = get_object_or_404(User, id=user_id, role='faculty', account_status='active', department__iexact=request.user.department)
    if request.method == 'POST':
        name = faculty_user.get_full_name() or faculty_user.username
        faculty_user.delete()
        return JsonResponse({'success': True, 'message': f"{name} removed."})
    return JsonResponse({'success': False, 'error': 'Invalid request method.'}, status=405)


@login_required
@role_required('depthead')
def admin_dashboard(request):
    today = date.today()
    month_start = today.replace(day=1)
    last_month_end = month_start - timedelta(days=1)
    last_month_start = last_month_end.replace(day=1)

    dept_code = request.user.department
    department = Department.objects.filter(code__iexact=dept_code).first()

    consultations_qs = ConsultationRequest.objects.filter(
        faculty__department_id__iexact=dept_code
    )

    total_this_month = consultations_qs.filter(date__gte=month_start).count()
    total_last_month = consultations_qs.filter(
        date__gte=last_month_start, date__lte=last_month_end
    ).count()
    total_change_pct = (
        round(((total_this_month - total_last_month) / total_last_month) * 100)
        if total_last_month > 0 else None
    )

    completed_this_month = consultations_qs.filter(
        date__gte=month_start, status='completed'
    ).count()
    completed_last_month = consultations_qs.filter(
        date__gte=last_month_start, date__lte=last_month_end, status='completed'
    ).count()
    completed_change_pct = (
        round(((completed_this_month - completed_last_month) / completed_last_month) * 100)
        if completed_last_month > 0 else None
    )

    faculty_qs = FacultyProfile.objects.filter(
        user__role='faculty',
        user__account_status='active',
        department_id__iexact=dept_code,
    )
    active_faculty_count = faculty_qs.count()
    available_now_count = faculty_qs.filter(current_status='available').count()
    available_now_pct = round((available_now_count / active_faculty_count) * 100) if active_faculty_count else 0

    return render(request, 'depthead/adminDashboard.html', {
        'department': department,
        'total_this_month': total_this_month,
        'total_change_pct': total_change_pct,
        'completed_this_month': completed_this_month,
        'completed_change_pct': completed_change_pct,
        'active_faculty_count': active_faculty_count,
        'available_now_count': available_now_count,
        'available_now_pct': available_now_pct,
    })


@login_required
@role_required('depthead')
def admin_faculty(request):
    faculty_users = User.objects.filter(
        role='faculty',
        department__iexact=request.user.department,
    ).select_related('faculty_profile').order_by('first_name', 'last_name', 'username')
    return render(request, 'depthead/adminFaculty.html', {
        'pending_faculty': faculty_users.filter(account_status='pending'),
        'active_faculty': faculty_users.filter(account_status='active'),
    })


@login_required
@role_required('depthead')
def faculty_schedule_template(request):
    """Download the CSV format used for department-head faculty uploads."""
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
    """Append a validated CSV schedule to a selected faculty member in this department."""
    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST requests are allowed.'}, status=405)
    faculty = get_object_or_404(
        FacultyProfile.objects.select_related('user'),
        faculty_id=faculty_id,
        department_id__iexact=request.user.department,
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
def student_behavior(request):
    dept_code = request.user.department

    consultations_qs = ConsultationRequest.objects.filter(
        faculty__department_id__iexact=dept_code
    )

    #consultation frequency over the last 6 months (line chart)
    today = date.today()
    month_starts = []
    cursor = today.replace(day=1)
    for _ in range(6):
        month_starts.append(cursor)
        cursor = (cursor - timedelta(days=1)).replace(day=1)
    month_starts.reverse()  #oldest to newest

    monthly_counts_qs = (
        consultations_qs.filter(date__gte=month_starts[0])
        .annotate(month=TruncMonth('date'))
        .values('month')
        .annotate(count=Count('request_id'))
    )
    monthly_lookup = {row['month']: row['count'] for row in monthly_counts_qs}

    monthly_data = []
    for m_start in month_starts:
        monthly_data.append({
            'month': m_start,
            'label': m_start.strftime('%b'),
            'count': monthly_lookup.get(m_start, 0),
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

    #peak reqyuest periods (all months)
    all_time_monthly = (
        consultations_qs.annotate(month=TruncMonth('date'))
        .values('month')
        .annotate(count=Count('request_id'))
        .order_by('-count')
    )
    if all_time_monthly:
        top_month_row = all_time_monthly[0]
        peak_period_label = top_month_row['month'].strftime('%B %Y')
        peak_period_count = top_month_row['count']
    else:
        peak_period_label = "No data"
        peak_period_count = 0

    #student request freq (top 10 students by request count)
    student_counts = (
        consultations_qs.values('user__id', 'user__first_name', 'user__last_name', 'user__username')
        .annotate(request_count=Count('request_id'))
        .order_by('-request_count')[:10]
    )
    student_frequency = []
    for row in student_counts:
        full_name = f"{row['user__first_name']} {row['user__last_name']}".strip()
        student_frequency.append({
            'name': full_name or row['user__username'],
            'count': row['request_count'],
        })

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
    profiles = FacultyProfile.objects.select_related('user').filter(
        user__role='faculty',
        user__account_status='active',
        department_id__iexact=request.user.department,
    )
    faculty_list = []
    for profile in profiles:
        label, css_class = STATUS_LABELS.get(profile.current_status, ('Unknown', 'status-unavailable'))
        faculty_list.append({
            'name': profile.user.get_full_name() or profile.user.username,
            'status_label': label,
            'status_class': css_class,
            'updated_at': profile.status_updated_at,
        })
    return render(request, 'depthead/facultyMonitoring.html', {'faculty_list': faculty_list})


@login_required
@role_required('depthead')
def department_settings(request):
    closure, _ = OfficeClosure.objects.get_or_create(
        department__iexact=request.user.department,
        defaults={'department': request.user.department}
    )
    if request.method == 'POST':
        form = OfficeClosureForm(request.POST, instance=closure)
        if form.is_valid():
            closure = form.save(commit=False)
            closure.department = request.user.department
            closure.updated_by = request.user
            closure.save()
            return JsonResponse({'success': True})
        errors = ' '.join(
            error for error_list in form.errors.values() for error in error_list
        )
        return JsonResponse({'success': False, 'error': errors or 'Unable to save closure settings.'})
    else:
        form = OfficeClosureForm(instance=closure)

    department_announcements = DepartmentAnnouncement.objects.filter(
        department__iexact=request.user.department,
        expiry__gt=timezone.now()
    )

    department = Department.objects.filter(code__iexact=request.user.department).first()

    return render(request, 'depthead/departmentSettings.html', {
        'closure_form': form,
        'department_announcements': department_announcements,
        'department': department,
    })


WEEKDAY_LABELS = {
    1: 'Sunday', 2: 'Monday', 3: 'Tuesday', 4: 'Wednesday',
    5: 'Thursday', 6: 'Friday', 7: 'Saturday',
}  # Django's ExtractWeekDay: 1=Sunday ... 7=Saturday


@login_required
@role_required('depthead')
def peak_analytics(request):
    dept_code = request.user.department

    consultations_qs = ConsultationRequest.objects.filter(
        faculty__department_id__iexact=dept_code
    )

    #Peak consultation hour (by start_time, excludes null times)
    hourly_counts = (
        consultations_qs.exclude(start_time__isnull=True)
        .annotate(hour=ExtractHour('start_time'))
        .values('hour')
        .annotate(count=Count('request_id'))
        .order_by('hour')
    )
    hourly_data = {h: 0 for h in range(7, 20)}  #7am-7pm
    for row in hourly_counts:
        if row['hour'] in hourly_data:
            hourly_data[row['hour']] = row['count']

    max_count = max(hourly_data.values()) if any(hourly_data.values()) else 1
    chart_bars = []
    bar_width = 32
    gap = 38
    start_x = 95
    max_bar_height = 160
    baseline_y = 250

    for i, (hour, count) in enumerate(hourly_data.items()):
        bar_height = round((count / max_count) * max_bar_height) if max_count else 0
        chart_bars.append({
            'x': start_x + i * gap,
            'y': baseline_y - bar_height,
            'height': bar_height,
            'label': f"{hour % 12 or 12}{'AM' if hour < 12 else 'PM'}",
            'count': count,
        })

    peak_hour_row = max(hourly_data.items(), key=lambda x: x[1]) if any(hourly_data.values()) else (None, 0)
    peak_hour_label = f"{peak_hour_row[0] % 12 or 12}{'AM' if peak_hour_row[0] < 12 else 'PM'}" if peak_hour_row[0] is not None else "No data"

    #peak consultation day
    weekday_counts = (
        consultations_qs.annotate(weekday=ExtractWeekDay('date'))
        .values('weekday')
        .annotate(count=Count('request_id'))
        .order_by('-count')
    )
    weekday_totals = {i: 0 for i in range(1, 8)}
    for row in weekday_counts:
        weekday_totals[row['weekday']] = row['count']

    if any(weekday_totals.values()):
        top_weekday_num = max(weekday_totals.items(), key=lambda x: x[1])[0]
        peak_day_label = WEEKDAY_LABELS.get(top_weekday_num, 'Unknown')
        peak_day_count = weekday_totals[top_weekday_num]
    else:
        peak_day_label = "No data"
        peak_day_count = 0

    # Build pie chart slices
    total_weekday_requests = sum(weekday_totals.values())
    pie_colors = ['#2563eb', '#3b82f6', '#60a5fa', '#93c5fd', '#1d4ed8', '#1e40af', '#bfdbfe']
    pie_slices = []
    if total_weekday_requests > 0:
        cx, cy, r = 110, 110, 90
        start_angle = -90  # start at top
        for i in range(1, 8):
            count = weekday_totals[i]
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
                'color': pie_colors[(i - 1) % len(pie_colors)],
                'label': WEEKDAY_LABELS[i],
                'count': count,
                'pct': round(fraction * 100),
            })
            start_angle = end_angle

    #supply-demand gap (today's requests / currently available faculty)
    today_request_count = consultations_qs.filter(date=date.today()).count()
    available_faculty_count = FacultyProfile.objects.filter(
        user__role='faculty',
        user__account_status='active',
        department_id__iexact=dept_code,
        current_status='available',
    ).count()

    #faculty consultation load distribution (top 5 faculty by request count)
    load_distribution = (
        consultations_qs.values('faculty__faculty_id', 'faculty__user__first_name', 'faculty__user__last_name', 'faculty__user__username')
        .annotate(request_count=Count('request_id'))
        .order_by('-request_count')[:5]
    )
    load_distribution_list = []
    for row in load_distribution:
        full_name = f"{row['faculty__user__first_name']} {row['faculty__user__last_name']}".strip()
        load_distribution_list.append({
            'name': full_name or row['faculty__user__username'],
            'count': row['request_count'],
        })

    max_count = max(hourly_data.values()) if any(hourly_data.values()) else 1
    chart_bars = []
    gap = 34
    start_x = 50
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
        'peak_hour_count': peak_hour_row[1],
        'peak_day_label': peak_day_label,
        'peak_day_count': peak_day_count,
        'pie_slices': pie_slices, 
        'today_request_count': today_request_count,
        'available_faculty_count': available_faculty_count,
        'load_distribution': load_distribution_list,
    })

@login_required
@role_required('depthead')
def faculty_trends(request):
    dept_code = request.user.department
    window_start = timezone.now() - timedelta(days=7)

    faculty_qs = FacultyProfile.objects.filter(
        user__role='faculty',
        user__account_status='active',
        department_id__iexact=dept_code,
    ).select_related('user')

    trends = []

    for profile in faculty_qs:
        name = profile.user.get_full_name() or profile.user.username

        #status update freq per day (rolling 7-day)
        status_change_count = StatusHistory.objects.filter(
            faculty=profile,
            changed_at__gte=window_start,
        ).count()
        updates_per_day = round(status_change_count / 7, 1)

        last_update_row = StatusHistory.objects.filter(faculty=profile).order_by('-changed_at').first()
        last_update_display = f"{timesince(last_update_row.changed_at)} ago" if last_update_row else "No data"

        #consultation completion rate
        all_requests = ConsultationRequest.objects.filter(faculty=profile)
        total_requests = all_requests.count()
        completed_requests = all_requests.filter(status='completed').count()
        completion_rate = round((completed_requests / total_requests) * 100) if total_requests else None

        #average response time hrs
        responded = all_requests.filter(approved_at__isnull=False).annotate(
            response_time=ExpressionWrapper(
                F('approved_at') - F('requested_at'), output_field=DurationField()
            )
        )
        avg_response = responded.aggregate(avg=Avg('response_time'))['avg']
        avg_response_hours = round(avg_response.total_seconds() / 3600, 1) if avg_response else None

        #availability rate (rolling 7-day)
        availability_rate = calculate_availability_rate(profile, window_start)

        trends.append({
            'name': name,
            'updates_per_day': updates_per_day,
            'last_update_display': last_update_display,
            'completion_rate': completion_rate,
            'avg_response_hours': avg_response_hours,
            'availability_rate': availability_rate,
        })

    
    #chart bars, one per faculty
    max_bar_height = 160
    baseline_y = 250
    bar_width = 40
    gap = 70
    start_x = 100
    chart_bars = []
    for i, t in enumerate(trends):
        rate = t['availability_rate'] or 0
        height = round((rate / 100) * max_bar_height)
        chart_bars.append({
            'x': start_x + i * gap,
            'y': baseline_y - height,
            'height': height,
            'label': t['name'].split()[0] if t['name'] else '',
            'rate': rate,
        })

    return render(request, 'depthead/facultyTrends.html', {
        'trends': trends,
        'chart_bars': chart_bars,
    })


def calculate_availability_rate(profile, window_start):
    now = timezone.now()

    carry_in = StatusHistory.objects.filter(
        faculty=profile,
        changed_at__lt=window_start,
    ).order_by('-changed_at').first()

    rows = list(StatusHistory.objects.filter(
        faculty=profile,
        changed_at__gte=window_start,
    ).order_by('changed_at'))

    if not rows and not carry_in:
        return None

    timeline = []
    if carry_in:
        timeline.append((window_start, carry_in.status))
    for row in rows:
        timeline.append((row.changed_at, row.status))

    if not timeline:
        return None

    total_seconds = 0
    available_seconds = 0
    for i, (start, status) in enumerate(timeline):
        end = timeline[i + 1][0] if i + 1 < len(timeline) else now
        duration = (end - start).total_seconds()
        if duration < 0:
            continue
        total_seconds += duration
        if status == 'available':
            available_seconds += duration

    if total_seconds == 0:
        return None

    return round((available_seconds / total_seconds) * 100)


@login_required
@role_required('depthead')
@require_POST
def create_announcement(request):
    if not request.user.department:
        return JsonResponse(
            {'success': False, 'error': "Your account has no department set. Contact a Super Admin."},
            status=400
        )

    form = DepartmentAnnouncementForm(request.POST)
    if not form.is_valid():
        errors = [e for error_list in form.errors.values() for e in error_list]
        return JsonResponse({'success': False, 'error': ' '.join(errors)}, status=400)

    announcement = form.save(commit=False)
    announcement.department = request.user.department
    announcement.posted_by = request.user
    announcement.save()
    notify_department_users(
        department=announcement.department,
        notification_type='announcement',
        title='Department announcement',
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
def edit_department_description(request):
    department = Department.objects.filter(code__iexact=request.user.department).first()
    if not department:
        messages.error(request, "Your department could not be found. Contact a Super Admin.")
        return redirect('depthead:department_settings')

    if request.method == 'POST':
        form = DepartmentDescriptionForm(request.POST, instance=department)
        if form.is_valid():
            form.save()
            messages.success(request, "Department description updated.")
        else:
            for error_list in form.errors.values():
                for error in error_list:
                    messages.error(request, error)

    return redirect('depthead:department_settings')
