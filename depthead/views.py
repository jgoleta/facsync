from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from core.decorators import role_required
from core.models import User, FacultyInvite, OfficeClosure, DepartmentAnnouncement, Department
from core.forms import DepartmentAnnouncementForm, DepartmentDescriptionForm
from django.contrib import messages
from .forms import FacultyInviteForm, OfficeClosureForm
from faculty.models import FacultyProfile, ConsultationRequest, StatusHistory
from django.utils import timezone
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from core.services import notify_department_users
from django.db.models import Count, Avg, F, ExpressionWrapper, DurationField
from django.db.models.functions import ExtractHour, ExtractWeekDay
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
            return redirect('depthead:pending_faculty_requests')
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
    return redirect('depthead:pending_faculty_requests')


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
    return render(request, 'depthead/adminFaculty.html')


@login_required
@role_required('depthead')
def student_behavior(request):
    return render(request, 'depthead/studentBehavior.html')


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
    if weekday_counts:
        top_day = weekday_counts[0]
        peak_day_label = WEEKDAY_LABELS.get(top_day['weekday'], 'Unknown')
        peak_day_count = top_day['count']
    else:
        peak_day_label = "No data"
        peak_day_count = 0

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

    return render(request, 'depthead/peakAnalytics.html', {
        'hourly_data': hourly_data,
        'chart_bars': chart_bars,
        'peak_hour_label': peak_hour_label,
        'peak_hour_count': peak_hour_row[1],
        'peak_day_label': peak_day_label,
        'peak_day_count': peak_day_count,
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