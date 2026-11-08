import csv
import json
import logging

from django.shortcuts import render, redirect, get_object_or_404
from django.template.loader import render_to_string
from django.contrib.auth.decorators import login_required
from apps.core.decorators import role_required
from apps.core.models import User, FacultyInvite, OfficeClosure, CollegeAnnouncement, College, Office
from apps.core.forms import CollegeAnnouncementForm, CollegeDescriptionForm, OfficeDescriptionForm
from django.contrib import messages
from .forms import FacultyInviteForm, OfficeClosureForm, SharedWindowForm
from apps.faculty.models import FacultyProfile, GoogleCalendarConnection, ScheduleEvent
from apps.faculty.services.google_calendar import GoogleCalendarError, create_google_event
from apps.faculty.services.schedule_duplicates import schedule_event_key
from apps.core.services import send_schedule_uploaded_email
from apps.faculty.views import (
    SCHEDULE_CSV_HEADERS, SCHEDULE_REQUIRED_FIELDS, SCHEDULE_TEMPLATE_FIELDS, _event_json,
    _parse_schedule_csv, _schedule_csv_row, schedule_template_headers,
    schedule_template_columns,
)
from django.utils import timezone
from django.http import HttpResponse, JsonResponse
from django.core.exceptions import PermissionDenied
from types import SimpleNamespace
from .scope import DepartmentScope, managed_departments
from apps.core.models import Department
from apps.superadmin.assignment_services import lock_departments
from django.db import transaction
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_POST
from django.views.decorators.http import require_GET
from apps.core.services import notify_college_users, send_faculty_invite_email, send_faculty_removed_email
from apps.core.services import send_announcement_email_to_faculty, send_closure_email_to_faculty
from django.views.decorators.cache import never_cache
from apps.core.faculty import mark_inactive_faculty
from datetime import timedelta, date
from apps.faculty.services.schedule_conflicts import occurs_on
from .services import (
    generate_ai_insights,
    get_college_analytics,
)
from .services.analytics import (
    get_base_consultation_queryset,
    get_faculty_trends,
    get_student_request_frequency_display,
    normalize_period,
    current_week_period,
    get_hourly_availability_snapshot,
)
from .services.schedule_availability import get_schedule_availability
from .services.shared_windows import planning_week, find_shared_windows


from .services.analytics_display import (
    student_reporting_period, peak_request_month, faculty_load_display, faculty_trends_display,
    consultation_topics_display, most_available_faculty_recommendation,
    schedule_availability_ai_summary,
)
from .services.analytics_browser import ANALYTICS_QUESTIONS, analytics_browser_answer

logger = logging.getLogger(__name__)


def _analytics_date_range(request, start, end, *, prefix=None):
    from .forms import AnalyticsDateRangeForm
    form = AnalyticsDateRangeForm(prefix=prefix, initial={'start_date': start, 'end_date': end})
    if any(form.add_prefix(field) in request.GET for field in ('start_date', 'end_date')):
        form = AnalyticsDateRangeForm(request.GET, prefix=prefix)
        if form.is_valid():
            return form, normalize_period(**form.cleaned_data)
    return form, normalize_period(start, end)


def _user_scope(request):
    scope = request.managed_scope
    return {'department_id__in': scope.department_ids} if isinstance(scope, DepartmentScope) else {'college__iexact': scope}


def _profile_scope(request):
    scope = request.managed_scope
    return {'user__department_id__in': scope.department_ids} if isinstance(scope, DepartmentScope) else {'college_id__iexact': scope}


def _target_department(request):
    units = managed_departments(request.user)
    chosen = request.POST.get('department_id') or request.GET.get('department_id')
    if chosen:
        if not str(chosen).isdecimal():
            raise PermissionDenied('Choose an assigned department.')
        return get_object_or_404(units, pk=chosen)
    if units.count() == 1:
        return units.get()
    raise PermissionDenied('Choose the department for this action.')


class DepartmentDescriptionForm(CollegeDescriptionForm):
    class Meta(CollegeDescriptionForm.Meta):
        model = Department


def _department_settings(request):
    if request.method == 'POST':
        unit = _target_department(request)
        with transaction.atomic():
            lock_departments([unit], request.user.school)
            closure = OfficeClosure.objects.filter(department=unit).first() or OfficeClosure(
                department=unit, college=unit.college.code if unit.college else '', school=request.user.school)
            was_closed = closure.is_closed
            form = OfficeClosureForm(request.POST, instance=closure)
            if not form.is_valid():
                return JsonResponse({'success': False, 'error': ' '.join(str(e) for errors in form.errors.values() for e in errors)}, status=400)
            closure = form.save(commit=False)
            closure.updated_by = request.user
            closure.save()
        if closure.is_closed and not was_closed:
            try:
                send_closure_email_to_faculty(closure)
            except Exception:
                logger.warning('Department closure email failed.')
        return JsonResponse({'success': True, 'is_closed': closure.is_closed})
    panels = []
    settings_data = {}
    for unit in managed_departments(request.user).select_related('college'):
        closure = OfficeClosure.objects.filter(department=unit).first() or OfficeClosure(department=unit, school=request.user.school)
        form = OfficeClosureForm(instance=closure, auto_id=f'department_{unit.pk}_%s')
        form.fields['is_closed'].widget.attrs['id'] = f'department_{unit.pk}_closed'
        panels.append({'unit': unit, 'closure_form': form})
        settings_data[str(unit.pk)] = {
            'college': unit.college.name if unit.college else 'No college',
            'description': unit.description,
            'is_closed': closure.is_closed,
            'reason': closure.reason,
            'closure_start': closure.closure_start.isoformat() if closure.closure_start else '',
            'closure_end': closure.closure_end.isoformat() if closure.closure_end else '',
        }
    return render(request, 'depthead/departmentSettings.html', {
        'panels': panels, 'departments': managed_departments(request.user), 'settings_data': settings_data,
        'announcement_form': CollegeAnnouncementForm(target_levels=True),
        'announcements': CollegeAnnouncement.objects.filter(department__in=managed_departments(request.user), expiry__gt=timezone.now()).select_related('department'),
    })


def _department_announcement(request):
    unit = _target_department(request)
    form = CollegeAnnouncementForm(request.POST, target_levels=True)
    if not form.is_valid():
        return JsonResponse({'success': False, 'error': ' '.join(str(e) for errors in form.errors.values() for e in errors)}, status=400)
    with transaction.atomic():
        lock_departments([unit], request.user.school)
        announcement = form.save(commit=False)
        announcement.department = unit
        announcement.college = unit.college.code if unit.college else ''
        announcement.posted_by = request.user
        announcement.save()
        roles = {'faculty': ('faculty',), 'students': ('student',), 'both': ('student', 'faculty')}[announcement.audience]
        notify_college_users(announcement.college, 'announcement', 'Department announcement', announcement.message,
            exclude_user_id=request.user.pk, roles=roles, department=unit, student_levels=announcement.student_levels)
    try:
        send_announcement_email_to_faculty(announcement)
    except Exception:
        logger.warning('Department announcement email failed.')
    return JsonResponse({'success': True, 'message': 'Announcement posted.'})

def _managed_unit(code):
    if isinstance(code, DepartmentScope):
        return SimpleNamespace(name=code.name, description='', schedule_template={})
    return College.objects.filter(code__iexact=code).first() or Office.objects.filter(code__iexact=code).first()


def _shared_window_context(request):
    planning = planning_week()
    planner_form = SharedWindowForm(request.GET if request.GET else None, week=planning)
    planner_result = None
    if not request.GET:
        day = planning['week_end'] if planning['ended'] else planning['today']
        planner_result = find_shared_windows(request.managed_scope, day, 120, now=planning['now'])
    elif planner_form.is_valid():
        planner_result = find_shared_windows(
            request.managed_scope, planner_form.cleaned_data['date'],
            planner_form.cleaned_data['duration'], now=planning['now'],
        )
    return {'planning': planning, 'planner_form': planner_form, 'planner_result': planner_result}


@login_required
@role_required('depthead')
@require_GET
@never_cache
def shared_windows_api(request):
    if not str(request.managed_scope or '').strip():
        return JsonResponse({'error': 'Your account has no departments assigned.'}, status=400)
    context = _shared_window_context(request)
    valid = not context['planner_form'].is_bound or not context['planner_form'].errors
    return JsonResponse({
        'html': render_to_string('depthead/partials/shared_windows_content.html', context, request=request),
    }, status=200 if valid else 400)


@login_required
@role_required('depthead')
def invite_faculty(request):
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    if request.method == 'POST':
        if not request.managed_scope:
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
        form = FacultyInviteForm(request.POST, instance=used_invite, user=request.user)
        if form.is_valid():
            invite = form.save(commit=False)
            unit = form.cleaned_data.get('department')
            invite.department = unit
            invite.college = (unit.college.code if unit.college else '') if unit else request.managed_scope
            invite.invited_by = request.user
            invite.used = False
            with transaction.atomic():
                if unit:
                    lock_departments([unit], request.user.school)
                invite.save()
            email_sent = False
            try:
                email_sent = send_faculty_invite_email(invite.email, unit.name if unit else invite.college)
            except Exception:
                logger.exception('Head faculty invitation email failed.')
            if is_ajax:
                return JsonResponse({
                    'success': True,
                    'message': f"Invitation created for {invite.email}.",
                    'email_sent': email_sent,
                }, status=201)
            messages.success(request, f"Invitation created for {invite.email}." + ('' if email_sent else ' Confirmation email could not be sent.'))
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
    faculty_user = get_object_or_404(User, id=user_id, role='faculty', account_status='active', **_user_scope(request))
    if request.method == 'POST':
        name = faculty_user.get_full_name() or faculty_user.username
        email = faculty_user.email
        faculty_user.delete()
        email_sent = False
        try:
            email_sent = send_faculty_removed_email(email, name)
        except Exception:
            email_sent = False
            logger.exception("Failed to send faculty removal email to %s", email)
        return JsonResponse({'success': True, 'message': f"{name} removed.", 'email_sent': email_sent})
    return JsonResponse({'success': False, 'error': 'Invalid request method.'}, status=405)


@login_required
@role_required('depthead')
def admin_dashboard(request):
    college_code = request.managed_scope
    college = _managed_unit(college_code)
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
        'analytics_questions': [
            {'metric': key, 'group': group, 'question': question}
            for key, (group, question) in ANALYTICS_QUESTIONS.items()
        ],
    })


@login_required
@role_required('depthead')
@require_GET
def ai_insights_api(request):
    """Return AI interpretation for the authenticated College Head's scope."""

    analytics = get_college_analytics(request.managed_scope)
    schedule_availability = get_schedule_availability(request.managed_scope)
    analytics['schedule_availability'] = schedule_availability_ai_summary(
        schedule_availability
    )
    result = generate_ai_insights(analytics)
    if result.get('available') is True:
        local_recommendations = [
            most_available_faculty_recommendation(schedule_availability),
        ]
        recommendations = result.setdefault('recommendations', [])
        for local_recommendation in local_recommendations:
            if local_recommendation and not any(
                item.get('title') == local_recommendation['title']
                for item in recommendations
                if isinstance(item, dict)
            ):
                recommendations.insert(0, local_recommendation)
    return JsonResponse(result)


@login_required
@role_required('depthead')
def admin_faculty(request):
    managed_units = managed_departments(request.user) if request.user.role == 'depthead' else []
    college = managed_units[0] if managed_units else _managed_unit(request.managed_scope)
    faculty_users = list(User.objects.filter(
        role='faculty',
        **_user_scope(request),
    ).select_related('faculty_profile').order_by('first_name', 'last_name', 'username'))

    mark_inactive_faculty(faculty_users)

    return render(request, 'depthead/adminFaculty.html', {
        'faculty_invite_form': FacultyInviteForm(user=request.user),
        'managed_departments': managed_units,
        'active_faculty': [u for u in faculty_users if u.account_status == 'active'],
        'schedule_template_fields': [
            {
                'field': field,
                'label': label,
                'value': (college.schedule_template or {}).get(field, field) if college else field,
            }
            for field, label in SCHEDULE_TEMPLATE_FIELDS
        ],
        'schedule_template_columns': schedule_template_columns(college.schedule_template if college else None),
    })


@login_required
@role_required('depthead')
def faculty_schedule_template(request):
    """Download the CSV format used for college-head faculty uploads."""
    response = HttpResponse(content_type='text/csv')
    if request.user.role == 'depthead':
        college = (
            _target_department(request)
            if request.GET.get('department_id')
            else managed_departments(request.user).first()
        )
    else:
        college = _managed_unit(request.managed_scope)
    headers = schedule_template_headers(college.schedule_template if college else None)
    response['Content-Disposition'] = 'attachment; filename=schedule_template.csv'
    writer = csv.writer(response)
    writer.writerow(headers)
    sample = {
        'OFFERING_ID': 'OFFERING-001', 'SUBJ_CODE': 'CS101', 'SECTION': 'A',
        'SUBJECT_TITLE': 'Introduction to Computing', 'UNITS': '3', 'LECTURE': '3',
        'LAB': '0', 'RECURRING_DAY': 'Monday', 'DAYFROM': '2026-08-17',
        'DAYTO': '2026-12-15', 'TIMEFROM': '10:30', 'TIMETO': '12:00', 'ROOM': 'Room 204',
    }
    writer.writerow([
        sample.get(column['key'], '')
        for column in schedule_template_columns(college.schedule_template if college else None)
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
        **_profile_scope(request),
        user__role='faculty',
    )
    college = faculty.user.department if faculty.user.department_id else _managed_unit(request.managed_scope)
    try:
        rows = _parse_schedule_csv(
            request.FILES.get('file'),
            college.schedule_template if college else None,
        )
    except ValueError as exc:
        detail = exc.args[0] if exc.args else 'Invalid CSV file.'
        errors = detail if isinstance(detail, list) else [detail]
        return JsonResponse({'error': 'The schedule was not saved.', 'errors': errors}, status=400)

    updated_at = timezone.now()
    with transaction.atomic():
        existing_keys = {
            schedule_event_key(values)
            for values in ScheduleEvent.objects.filter(faculty=faculty).values(
                'title', 'date', 'day_of_week', 'start_month', 'end_month',
                'recurrence_start_date', 'recurrence_end_date', 'start_time', 'end_time',
            )
        }
        new_rows = []
        skipped_count = 0
        for row in rows:
            key = schedule_event_key(row)
            if key in existing_keys:
                skipped_count += 1
                continue
            existing_keys.add(key)
            new_rows.append(row)
        events = ScheduleEvent.objects.bulk_create([
            ScheduleEvent(
                faculty=faculty,
                title=row['title'],
                offering_id=row['offering_id'],
                subject_code=row['subject_code'],
                section=row['section'],
                units=row['units'],
                lecture=row['lecture'],
                lab=row['lab'],
                extra_attributes=row.get('extra_attributes', {}),
                uploaded_by=request.user,
                is_csv_upload=True,
                description=row['description'],
                location=row['room'],
                schedule_status=row['status'],
                event_type=row['event_type'],
                date=row['date'],
                day_of_week=row['day_of_week'],
                start_month=row['start_month'],
                end_month=row['end_month'],
                recurrence_start_date=row['recurrence_start_date'],
                recurrence_end_date=row['recurrence_end_date'],
                start_time=row['start_time'],
                end_time=row['end_time'],
                managed_by_facsync=True,
                sync_state='local',
            )
            for row in new_rows
        ])
        if events:
            faculty.schedule_last_updated_at = updated_at
            faculty.save(update_fields=['schedule_last_updated_at'])

    calendar_sync = {
        'requested': request.POST.get('sync_to_google') == 'true',
        'status': 'not_requested',
        'synced_count': 0,
    }
    if calendar_sync['requested']:
        connection = GoogleCalendarConnection.objects.filter(user=faculty.user).first()
        if connection is None:
            calendar_sync.update(
                status='not_connected',
                message='The faculty member has not connected a Google Calendar.',
            )
        else:
            try:
                for event in events:
                    google_event = create_google_event(connection, event)
                    event.google_event_id = google_event.get('id')
                    event.google_calendar_id = connection.calendar_id
                    event.sync_state = 'synced'
                    event.sync_error = ''
                    event.save(update_fields=[
                        'google_event_id', 'google_calendar_id', 'sync_state', 'sync_error',
                    ])
                    calendar_sync['synced_count'] += 1
                calendar_sync['status'] = 'synced'
            except GoogleCalendarError as exc:
                calendar_sync.update(status='failed', message=str(exc))
                logger.exception(
                    'Failed to sync uploaded schedule to Google Calendar for faculty %s',
                    faculty.faculty_id,
                )

    email_sent = False
    try:
        email_sent = send_schedule_uploaded_email(faculty.user, events, request.user)
    except Exception:
        logger.exception('Failed to send schedule upload email for faculty %s', faculty.faculty_id)

    return JsonResponse({
        'message': f'Schedule uploaded for {faculty.user.get_full_name() or faculty.user.username}. {len(events)} row(s) added.',
        'email_sent': email_sent,
        'added_count': len(events),
        'skipped_count': skipped_count,
        'calendar_sync': calendar_sync,
        'last_updated_at': updated_at.isoformat(),
        'preview': [_schedule_csv_row(event) for event in events],
        'template_columns': schedule_template_columns(college.schedule_template if college else None),
        'events': [_event_json(event) for event in events],
    }, status=201)


@login_required
@role_required('depthead')
def view_faculty_schedule_preview(request, faculty_id):
    """Return the uploaded FacSync schedule rows for a faculty member."""
    faculty = get_object_or_404(
        FacultyProfile.objects.select_related('user'),
        faculty_id=faculty_id,
        **_profile_scope(request),
        user__role='faculty',
    )
    events = list(
        ScheduleEvent.objects.filter(
            faculty=faculty,
            is_csv_upload=True,
        ).select_related('uploaded_by').order_by('id')
    )
    rows = []
    for event in events:
        uploader = event.uploaded_by
        rows.append({
            **_schedule_csv_row(event),
            'id': event.pk,
            'uploader_label': (
                f'Uploaded by {uploader.get_full_name() or uploader.username}'
                if uploader else 'Uploader unknown'
            ),
        })
    return JsonResponse({
        'faculty_id': faculty.faculty_id,
        'faculty_name': faculty.user.get_full_name() or faculty.user.username,
        'last_updated_at': faculty.schedule_last_updated_at.isoformat() if faculty.schedule_last_updated_at else None,
        'preview': rows,
        'template_columns': schedule_template_columns(
            (faculty.user.department.schedule_template if faculty.user.department_id else None)
        ),
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
        **_profile_scope(request),
        user__role='faculty',
    )
    with transaction.atomic():
        deleted_count, _ = ScheduleEvent.objects.filter(
            faculty=faculty,
            is_csv_upload=True,
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
    college_code = request.managed_scope
    month_starts, today = student_reporting_period()
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

    peak_period_label, peak_period_count = peak_request_month(analytics['request_patterns']['monthly_trend'])
    frequency_form, request_period = _analytics_date_range(request, month_starts[0], today, prefix='frequency')
    consultations_qs = get_base_consultation_queryset(college_code).filter(
        requested_at__gte=request_period.start_datetime,
        requested_at__lt=request_period.end_datetime_exclusive,
    )
    student_frequency = get_student_request_frequency_display(consultations_qs)

    return render(request, 'depthead/studentBehavior.html', {
        'line_points': line_points,
        'polyline_str': polyline_str,
        'peak_period_label': peak_period_label,
        'peak_period_count': peak_period_count,
        'student_frequency': student_frequency,
        'frequency_form': frequency_form,
        'frequency_start': request_period.start_date,
        'frequency_end': request_period.end_date,
        'consultation_topics': consultation_topics_display(analytics['consultations']),
        'topics_period_start': month_starts[0],
        'topics_period_end': today,
    })


STATUS_LABELS = {
    'not_set': ('Not Set', 'status-not-set'),
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
        **_profile_scope(request),
    )
    faculty_list = []
    for profile in profiles:
        label, css_class = STATUS_LABELS.get(profile.current_status, ('Unknown', 'status-unavailable'))
        last_login = profile.user.last_login
        is_inactive = last_login is None or last_login < inactivity_threshold
        faculty_list.append({
            'faculty_id': profile.faculty_id,
            'name': profile.user.get_full_name() or profile.user.username,
            'photo_url': profile.user.avatar_url,
            'status_label': label,
            'status_class': css_class,
            'updated_at': profile.status_updated_at,
            'is_inactive': is_inactive,
            'last_login': last_login,
        })
    return render(request, 'depthead/facultyMonitoring.html', {
        'faculty_list': faculty_list,
        'status_counts': _monitoring_status_counts(faculty_list),
    })


def _monitoring_status_counts(faculty_list):
    """Summarize the same college-scoped faculty shown in monitoring."""
    return [
        {
            'key': key,
            'label': STATUS_LABELS[key][0],
            'count': sum(item['status_class'] == STATUS_LABELS[key][1] for item in faculty_list),
        }
        for key in ('available', 'busy', 'virtual_only', 'on_leave', 'unavailable')
    ]


@login_required
@role_required('depthead')
def college_settings(request):
    if request.user.role == 'depthead':
        return _department_settings(request)
    if not request.managed_scope:
        return JsonResponse({'success': False, 'error': 'Your account has no departments assigned.'}, status=400)
    closure, _ = OfficeClosure.objects.get_or_create(
        **_user_scope(request),
        defaults={'college': request.managed_scope}
    )
    if request.method == 'POST':
        form = OfficeClosureForm(request.POST, instance=closure)
        if form.is_valid():
            closure = form.save(commit=False)
            closure.college = request.managed_scope
            closure.updated_by = request.user
            was_closed = OfficeClosure.objects.values_list('is_closed', flat=True).get(pk=closure.pk)
            closure.save()
            if not was_closed and closure.is_closed:
                try:
                    send_closure_email_to_faculty(closure)
                except Exception:
                    logger.exception('Failed to send closure emails for college %s', closure.college)
            return JsonResponse({'success': True, 'is_closed': closure.is_closed})
        errors = ' '.join(
            error for error_list in form.errors.values() for error in error_list
        )
        return JsonResponse({'success': False, 'error': errors or 'Unable to save closure settings.'})
    else:
        form = OfficeClosureForm(instance=closure)

    college_announcements = CollegeAnnouncement.objects.filter(
        **_user_scope(request),
        expiry__gt=timezone.now()
    )

    college = _managed_unit(request.managed_scope)

    return render(request, 'depthead/collegeSettings.html', {
        'closure_form': form,
        'college_announcements': college_announcements,
        'announcement_form': CollegeAnnouncementForm(),
        'college': college,
        'schedule_template_fields': [
            {
                'field': field,
                'label': label,
                'value': (college.schedule_template or {}).get(field, field) if college else field,
            }
            for field, label in SCHEDULE_TEMPLATE_FIELDS
        ],
    })


WEEKDAY_LABELS = {
    1: 'Sunday', 2: 'Monday', 3: 'Tuesday', 4: 'Wednesday',
    5: 'Thursday', 6: 'Friday', 7: 'Saturday',
}  # Django's ExtractWeekDay: 1=Sunday ... 7=Saturday


@login_required
@role_required('depthead')
def peak_analytics(request):
    college_code = request.managed_scope
    week = current_week_period()
    period_form, period = _analytics_date_range(request, week.start_date, week.end_date)
    analytics = get_college_analytics(college_code, period.start_date, period.end_date)
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

    load_distribution_list = faculty_load_display(analytics)
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
        'reporting_start': date.fromisoformat(analytics['period']['start_date']),
        'reporting_end': date.fromisoformat(analytics['period']['end_date']),
        'reporting_timezone': analytics['period']['timezone'],
        'period_form': period_form,
        'hourly_data': hourly_data,
        'chart_bars': chart_bars,
        'peak_hour_label': peak_hour_label,
        'peak_hour_count': peak_hour_count,
        'peak_day_label': peak_day_label,
        'peak_day_count': peak_day_count,
        'pie_slices': pie_slices, 
        'hourly_snapshot': get_hourly_availability_snapshot(college_code),
        'load_distribution': load_distribution_list,
        'analysis_period': analytics['period'],
    })

@login_required
@role_required('depthead')
def faculty_trends(request):
    college_code = request.managed_scope
    week = current_week_period()
    analytics = get_faculty_trends(college_code, week.start_date, week.end_date, status_period=True)
    trends = faculty_trends_display(analytics)
    for row in trends:
        if row["last_update_display"] == "No data":
            row["last_update_display"] = "No updates this week"

    # Preserve fractional rates; CSS gives tiny positive values a visible marker.
    chart_bars = []
    for t in trends:
        rate = t['availability_rate']
        chart_bars.append({
            'label': t['name'],
            'rate': rate,
            'has_data': rate is not None,
        })

    planner_context = _shared_window_context(request)

    return render(request, 'depthead/facultyTrends.html', {
        'trends': trends,
        'chart_bars': chart_bars,
        'schedule_availability': get_schedule_availability(college_code),
        **planner_context,
        'consultation_start': date.fromisoformat(analytics['consultation_period']['start_date']),
        'consultation_end': date.fromisoformat(analytics['consultation_period']['end_date']),
    })


@login_required
@role_required('depthead')
@require_POST
def create_announcement(request):
    if request.user.role == 'depthead':
        return _department_announcement(request)
    if not request.managed_scope:
        return JsonResponse(
            {'success': False, 'error': "Your account has no college set. Contact a Super Admin."},
            status=400
        )

    form = CollegeAnnouncementForm(request.POST)
    if not form.is_valid():
        errors = [e for error_list in form.errors.values() for e in error_list]
        return JsonResponse({'success': False, 'error': ' '.join(errors)}, status=400)

    announcement = form.save(commit=False)
    announcement.college = request.managed_scope
    announcement.posted_by = request.user
    announcement.save()
    notify_college_users(
        college=announcement.college,
        notification_type='announcement',
        title='College announcement',
        message=announcement.message,
        url='',
        exclude_user_id=request.user.id,
        roles={'faculty': ('faculty',), 'students': ('student',), 'both': ('student', 'faculty')}[announcement.audience],
    )

    try:
        send_announcement_email_to_faculty(announcement)
    except Exception:
        logger.exception('Failed to send announcement emails for announcement %s', announcement.pk)

    return JsonResponse({
        'success': True,
        'announcement': {
            'message': announcement.message,
            'audience': announcement.audience,
            'audience_label': announcement.get_audience_display(),
            'posted_at': announcement.posted_at.strftime('%b %d, %Y'),
            'expiry': announcement.expiry.strftime('%b %d, %Y'),
        }
    })


@login_required
@role_required('depthead')
def edit_college_description(request):
    college = _target_department(request) if request.user.role == 'depthead' else _managed_unit(request.managed_scope)
    if not college:
        messages.error(request, "Your college could not be found. Contact a Super Admin.")
        return redirect('depthead:college_settings')

    if request.method == 'POST':
        form_class = OfficeDescriptionForm if isinstance(college, Office) else DepartmentDescriptionForm if isinstance(college, Department) else CollegeDescriptionForm
        form = form_class(request.POST, instance=college)
        if form.is_valid():
            form.save()
            if isinstance(college, Department) and request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': True, 'message': 'Department description updated.'})
            messages.success(request, "Office description updated." if isinstance(college, Office) else "College description updated.")
        else:
            if isinstance(college, Department) and request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'error': ' '.join(str(e) for errors in form.errors.values() for e in errors)}, status=400)
            for error_list in form.errors.values():
                for error in error_list:
                    messages.error(request, error)

    return redirect('depthead:college_settings')


@login_required
@role_required('depthead')
@csrf_protect
def save_schedule_template(request):
    """Save the College Head's CSV labels for future schedule uploads."""
    if request.method != 'POST':
        return HttpResponse(status=405)
    college = _managed_unit(request.managed_scope)
    if not college:
        messages.error(request, 'Your college could not be found. Contact a Super Admin.')
        return redirect('depthead:college_settings')

    try:
        submitted_columns = json.loads(request.POST.get('template_columns', '[]'))
    except (TypeError, ValueError):
        submitted_columns = []
    if not isinstance(submitted_columns, list) or not submitted_columns or len(submitted_columns) > 32:
        messages.error(request, 'Add between 1 and 32 schedule template attributes.')
        return redirect('depthead:admin_faculty')

    columns = []
    used = set()
    for item in submitted_columns:
        if not isinstance(item, dict):
            messages.error(request, 'Invalid schedule template attribute.')
            return redirect('depthead:admin_faculty')
        field = str(item.get('key', '')).strip().upper()
        label = ' '.join(str(item.get('label', '')).split())
        if not field or not label or len(label) > 64:
            messages.error(request, 'Every schedule template attribute needs a name of 1 to 64 characters.')
            return redirect('depthead:admin_faculty')
        if field not in SCHEDULE_CSV_HEADERS and not field.startswith('CUSTOM_'):
            messages.error(request, 'Invalid schedule template attribute.')
            return redirect('depthead:admin_faculty')
        key = label.casefold()
        if field in used or key in used:
            messages.error(request, 'Schedule template attributes must be unique.')
            return redirect('depthead:admin_faculty')
        used.add(field)
        used.add(key)
        columns.append({'key': field, 'label': label})

    missing_required = SCHEDULE_REQUIRED_FIELDS.difference(column['key'] for column in columns)
    if missing_required:
        messages.error(request, 'Required schedule attributes cannot be deleted.')
        return redirect('depthead:admin_faculty')

    targets = list(managed_departments(request.user)) if request.user.role == 'depthead' else []
    # Older faculty accounts may still be assigned only through their college.
    # Preserve that path when no department assignments exist yet.
    if not targets and college and hasattr(college, 'save'):
        targets = [college]
    if not targets and request.user.role == 'depthead' and request.user.college:
        legacy_college = College.objects.filter(code__iexact=request.user.college).first()
        if legacy_college:
            targets = [legacy_college]
    if not targets:
        messages.error(request, 'No department or college was found for this admin account.')
        return redirect('depthead:admin_faculty')
    with transaction.atomic():
        for target in targets:
            target.schedule_template = {'columns': columns}
            target.save(update_fields=['schedule_template'])
    messages.success(request, 'Schedule upload template updated.')
    return redirect('depthead:admin_faculty')

@login_required
@role_required('depthead')
def faculty_monitoring_data(request):
    inactivity_threshold = timezone.now() - timedelta(days=30)
    profiles = FacultyProfile.objects.select_related('user').filter(
        user__role='faculty',
        user__account_status='active',
        **_profile_scope(request),
    )
    faculty_list = []
    for profile in profiles:
        label, css_class = STATUS_LABELS.get(profile.current_status, ('Unknown', 'status-unavailable'))
        last_login = profile.user.last_login
        is_inactive = last_login is None or last_login < inactivity_threshold
        faculty_list.append({
            'id': profile.faculty_id,
            'name': profile.user.get_full_name() or profile.user.username,
            'photo_url': profile.user.avatar_url,
            'status_label': label,
            'status_class': css_class,
            'updated_at_iso': profile.status_updated_at.isoformat() if profile.status_updated_at else None,
            'is_inactive': is_inactive,
        })
    return JsonResponse({
        'faculty_list': faculty_list,
        'status_counts': _monitoring_status_counts(faculty_list),
    })


@login_required
@role_required('depthead')
@require_GET
def faculty_monitoring_schedule(request, faculty_id):
    """Return one faculty member's schedule occurrences for the current month."""
    faculty = get_object_or_404(
        FacultyProfile.objects.select_related('user'),
        faculty_id=faculty_id,
        user__role='faculty',
        **_profile_scope(request),
    )
    month_start = timezone.localdate().replace(day=1)
    month_end = (
        date(month_start.year + 1, 1, 1)
        if month_start.month == 12
        else date(month_start.year, month_start.month + 1, 1)
    )
    events = ScheduleEvent.objects.filter(faculty=faculty).order_by('date', 'start_time', 'title')
    occurrences = []
    day = month_start
    while day < month_end:
        for event in events:
            if not occurs_on(event, day):
                continue
            payload = _event_json(event)
            payload['id'] = f'{event.pk}:{day.isoformat()}'
            payload['date'] = day.isoformat()
            payload['is_recurring'] = event.date is None
            occurrences.append(payload)
        day += timedelta(days=1)

    occurrences.sort(key=lambda item: (item['date'], item['start_time'] or '', item['title']))
    return JsonResponse({
        'faculty_id': faculty.faculty_id,
        'faculty_name': faculty.user.get_full_name() or faculty.user.username,
        'month_label': month_start.strftime('%B %Y'),
        'events': occurrences,
    })


@login_required
@role_required('depthead')
@require_GET
@never_cache
def closure_status(request):
    if request.user.role == 'depthead':
        unit = _target_department(request)
        return JsonResponse({'is_closed': OfficeClosure.objects.filter(department=unit, is_closed=True).exists()})
    if not request.managed_scope:
        return JsonResponse({'error': 'Your account has no departments assigned.'}, status=400)
    state = OfficeClosure.objects.filter(**_user_scope(request)).values_list('is_closed', flat=True).first()
    return JsonResponse({'is_closed': bool(state)})


@login_required
@role_required('depthead')
@require_GET
@never_cache
def analytics_browser_api(request):
    if not request.managed_scope:
        return JsonResponse({'error': 'Your account has no departments assigned.'}, status=400)
    metric = request.GET.get('metric', '')
    if metric not in ANALYTICS_QUESTIONS:
        return JsonResponse({'error': 'Unknown analytics question.'}, status=400)
    try:
        return JsonResponse(analytics_browser_answer(metric, request.managed_scope))
    except Exception:
        logger.exception('Unable to load analytics browser metric %s', metric)
        return JsonResponse({'error': "Sorry, I couldn't load that right now."}, status=500)


@login_required
@role_required('depthead')
@require_GET
@never_cache
def hourly_availability(request):
    if not request.managed_scope:
        return JsonResponse({'error': 'No departments assigned.'}, status=400)
    return JsonResponse(get_hourly_availability_snapshot(request.managed_scope))
