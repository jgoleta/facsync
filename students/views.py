import json
import json
import uuid
from datetime import date, datetime, time, timedelta
from core.models import OfficeClosure, DepartmentAnnouncement
from core.services import create_notification, get_active_announcements

from django.contrib.auth.decorators import login_required
from core.decorators import role_required
from django.db import transaction
from django.http import HttpResponse, HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_protect

from core.departments import get_department_label
from faculty.models import ConsultationRequest, FacultyProfile, ScheduleEvent, WalkInQueue
from .models import FacultyStatusSubscription
from faculty.facultyServices.googleCalendarService import refresh_faculty_status


def _json_body(request):
    try:
        payload = json.loads(request.body.decode('utf-8'))
    except (TypeError, ValueError, UnicodeDecodeError):
        raise ValueError('Invalid JSON')
    if not isinstance(payload, dict):
        raise ValueError('Invalid JSON')
    return payload


def _walk_in_json(queue):
    return {
        'queue_id': queue.queue_id,
        'faculty_id': queue.faculty.faculty_id,
        'status': queue.status,
        'position': queue.position,
        'joined_at': queue.joined_at.isoformat(),
        'notified_at': queue.notified_at.isoformat() if queue.notified_at else None,
        'served_at': queue.served_at.isoformat() if queue.served_at else None,
        'faculty_note': queue.faculty_note,
    }

def _closed_department_map():
    closures = OfficeClosure.objects.filter(is_closed=True)
    result = {}
    for c in closures:
        label = get_department_label(c.department) or c.department
        result[label] = c.reason or f"{label} is currently closed."
    return result

def _faculty_for_schedule(request):
    faculty_id = request.GET.get('faculty_id')
    faculty_name = (request.GET.get('faculty') or '').strip()
    faculty = FacultyProfile.objects.select_related('user').filter(faculty_id=faculty_id).first() if faculty_id else None
    if faculty is None and faculty_name:
        faculty = FacultyProfile.objects.select_related('user').filter(
            user__first_name__iexact=faculty_name,
        ).first()
        if faculty is None:
            faculty = FacultyProfile.objects.select_related('user').filter(
                user__username__iexact=faculty_name,
            ).first()
    return faculty


def _faculty_directory(closed_department_codes=None, student=None):
    closed_department_codes = closed_department_codes or set()
    subscribed_faculty_ids = set()
    if student:
        subscribed_faculty_ids = set(
            FacultyStatusSubscription.objects.filter(student=student)
            .values_list('faculty_id', flat=True)
        )
    directory = []
    for faculty in FacultyProfile.objects.select_related('user').all():
        refresh_faculty_status(faculty)
        directory.append({
            'faculty_id': faculty.faculty_id,
            'name': faculty.user.get_full_name() or faculty.user.username,
            'department': faculty.department_name,
            'status': faculty.current_status,
            'note': 'Department closed' if faculty.department_id in closed_department_codes else faculty.status_note,
            'walk_ins_enabled': faculty.walk_ins_enabled,
            'updated_at': faculty.status_updated_at.isoformat() if faculty.status_updated_at else None,
            'is_dept_closed': faculty.department_id in closed_department_codes,
            'is_subscribed': faculty.faculty_id in subscribed_faculty_ids,
        })
    return directory

def _closed_department_codes():
    return set(OfficeClosure.objects.filter(is_closed=True).values_list('department', flat=True))

@login_required
@role_required('student')
def dashboard(request):
    faculty_directory = _faculty_directory(_closed_department_codes(), request.user)
    closed_departments = _closed_department_map()
    return render(request, 'students/dashboardStudent.html', {
        'faculty_directory': faculty_directory,
        'closed_departments': closed_departments,
        'announcements': get_active_announcements(request.user.department),
    })

@login_required
@role_required('student')
def view_schedule(request):
    faculty = _faculty_for_schedule(request)
    if faculty:
        refresh_faculty_status(faculty)
    closure = None
    if faculty:
        closure = OfficeClosure.objects.filter(department=faculty.department_id, is_closed=True).first()
    return render(request, 'students/viewSchedule.html', {
        'selected_faculty': faculty,
        'department_closure': closure,
        'is_subscribed': bool(
            faculty and FacultyStatusSubscription.objects.filter(
                student=request.user,
                faculty=faculty,
            ).exists()
        ),
    })


def _schedule_event_json(event):
    """Serialize a faculty schedule event for student calendar clients."""
    return {
        'id': event.pk,
        'title': event.title,
        'description': event.description,
        'location': event.location,
        'status': event.schedule_status or event.event_type,
        'event_type': event.event_type,
        'date': event.date.isoformat() if event.date else None,
        'is_recurring': event.date is None,
        'day_of_week': '' if event.day_of_week == 'none' else event.day_of_week,
        'start_month': event.start_month,
        'end_month': event.end_month,
        'start_time': event.start_time.isoformat() if event.start_time else None,
        'end_time': event.end_time.isoformat() if event.end_time else None,
    }


@login_required
@role_required('student')
def api_schedule_events(request):
    """Return the selected faculty member's published schedule events."""
    if request.method != 'GET':
        return HttpResponse(status=405)

    faculty = get_object_or_404(FacultyProfile, faculty_id=request.GET.get('faculty_id'))
    events = ScheduleEvent.objects.filter(faculty=faculty).order_by('date', 'start_time')
    return JsonResponse({
        'faculty_id': faculty.faculty_id,
        'events': [_schedule_event_json(event) for event in events],
    })

@login_required
@role_required('student')
def active_announcements(request):
    qs = DepartmentAnnouncement.objects.filter(
        department=request.user.department,
        expiry__gt=timezone.now()
    )
    return JsonResponse({
        'announcements': [
            {
                'department': a.get_department_display(),
                'message': a.message,
                'posted_at': a.posted_at.strftime('%b %d, %Y'),
            }
            for a in qs
        ]
    })

@login_required
@role_required('student')
def consultation_requests(request):
    """Show only the signed-in student's consultation requests."""
    consultations = ConsultationRequest.objects.filter(
        user=request.user,
    ).select_related('faculty__user')
    return render(request, 'students/consultationRequests.html', {
        'consultations': consultations,
    })


def _consultation_json(consultation):
    """Serialize a student's consultation for the booking and listing APIs."""
    return {
        'request_id': consultation.request_id,
        'faculty_name': consultation.faculty.user.get_full_name() or consultation.faculty.user.username,
        'status': consultation.status,
        'status_label': consultation.get_status_display(),
        'date': consultation.date.isoformat(),
        'start_time': consultation.start_time.isoformat() if consultation.start_time else None,
        'end_time': consultation.end_time.isoformat() if consultation.end_time else None,
        'student_message': consultation.student_message,
        'faculty_note': consultation.faculty_note,
    }


@login_required
@role_required('student')
@csrf_protect
def api_consultation_requests(request):
    """List or create consultation requests owned by the signed-in student."""
    consultations = ConsultationRequest.objects.filter(
        user=request.user,
    ).select_related('faculty__user')

    if request.method == 'GET':
        return JsonResponse({'consultations': [_consultation_json(item) for item in consultations]})
    if request.method != 'POST':
        return HttpResponse(status=405)

    try:
        payload = _json_body(request)
        faculty_id = str(payload.get('faculty_id') or '').strip()
        date_value = date.fromisoformat(str(payload.get('date') or ''))
        start_time = time.fromisoformat(str(payload.get('start_time') or ''))
    except (TypeError, ValueError, KeyError) as exc:
        return JsonResponse({'error': 'A valid faculty, date, and start time are required.'}, status=400)

    faculty = get_object_or_404(FacultyProfile.objects.select_related('user'), faculty_id=faculty_id)
    if OfficeClosure.objects.filter(department=faculty.department_id, is_closed=True).exists():
        return JsonResponse({'error': 'This department is currently closed and not accepting consultation requests.'}, status=409)
    requested_end_time = payload.get('end_time')
    try:
        end_time = time.fromisoformat(str(requested_end_time)) if requested_end_time else (
            datetime.combine(date_value, start_time) + timedelta(hours=1)
        ).time()
    except (TypeError, ValueError):
        return JsonResponse({'error': 'Invalid consultation end time.'}, status=400)

    if end_time <= start_time:
        return JsonResponse({'error': 'The consultation must end after it starts.'}, status=400)

    consultation = ConsultationRequest.objects.create(
        request_id=uuid.uuid4().hex,
        user=request.user,
        faculty=faculty,
        date=date_value,
        start_time=start_time,
        end_time=end_time,
        student_message=str(payload.get('message') or '').strip(),
    )
    create_notification(
        recipient=faculty.user,
        notification_type='consultation_request',
        title='New consultation request',
        message=(
            f'{request.user.get_full_name() or request.user.username} requested a consultation '
            f'on {consultation.date.strftime("%B %d, %Y")}.'
        ),
        url='/faculty/dashboard/',
    )
    return JsonResponse(_consultation_json(consultation), status=201)

@login_required
@role_required('student')
def home(request):
    """Render student summary counts and the student's department announcement."""
    today = timezone.localdate()
    current_time = timezone.localtime().time()
    upcoming_bookings = ConsultationRequest.objects.filter(
        user=request.user,
        status='approved',
    ).select_related('faculty').order_by('date', 'start_time')
    upcoming_booking_count = sum(
        1 for booking in upcoming_bookings
        if booking.date > today
        or (booking.date == today and (booking.start_time is None or booking.start_time >= current_time))
    )

    student_department = get_department_label(request.user.department)
    department_announcement = DepartmentAnnouncement.objects.filter(
        department__iexact=request.user.department or '',
        expiry__gt=timezone.now(),
    ).first()
    available_faculty_count = 0
    if student_department:
        for faculty in FacultyProfile.objects.select_related('user').all():
            # Match canonical department names so CCS and ccs records remain compatible.
            if get_department_label(faculty.department_id) != student_department:
                continue
            refresh_faculty_status(faculty)
            if faculty.current_status == 'available':
                available_faculty_count += 1

    return render(request, 'students/homeStudent.html', {
        'upcoming_booking_count': upcoming_booking_count,
        'available_faculty_count': available_faculty_count,
        'student_department': student_department,
        'department_announcement': department_announcement,
    })


@login_required
@role_required('student')
def api_faculty_statuses(request):
    if request.method != 'GET':
        return HttpResponse(status=405)
    return JsonResponse({
        'faculty': _faculty_directory(_closed_department_codes(), request.user),
        'closed_departments': _closed_department_map(),
    })


@login_required
@role_required('student')
@csrf_protect
def api_faculty_status_subscription(request, faculty_id):
    if request.method not in {'GET', 'POST', 'DELETE'}:
        return HttpResponse(status=405)

    faculty = get_object_or_404(FacultyProfile, faculty_id=faculty_id)
    subscription = FacultyStatusSubscription.objects.filter(
        student=request.user,
        faculty=faculty,
    ).first()

    if request.method == 'GET':
        return JsonResponse({'subscribed': subscription is not None})

    if request.method == 'POST':
        FacultyStatusSubscription.objects.get_or_create(
            student=request.user,
            faculty=faculty,
        )
        return JsonResponse({'subscribed': True})

    if subscription:
        subscription.delete()
    return JsonResponse({'subscribed': False})


@login_required
@role_required('student')
def api_walk_in_status(request):
    """Return walk-in availability and the signed-in student's queue state."""
    if request.method != 'GET':
        return HttpResponse(status=405)

    faculty_id = request.GET.get('faculty_id')
    faculty = get_object_or_404(FacultyProfile.objects.select_related('user'), faculty_id=faculty_id)
    refresh_faculty_status(faculty)
    queue = WalkInQueue.objects.filter(
        faculty=faculty,
        user=request.user,
        status__in=['waiting', 'called'],
    ).first()
    return JsonResponse({
        'faculty_id': faculty.faculty_id,
        'faculty_name': faculty.user.get_full_name() or faculty.user.username,
        'faculty_status': faculty.current_status,
        'walk_ins_enabled': faculty.walk_ins_enabled,
        'queue': _walk_in_json(queue) if queue else None,
    })


@login_required
@role_required('student')
@csrf_protect
def api_join_walk_in_queue(request):
    """Join a faculty member's walk-in queue only while walk-ins are enabled."""
    if request.method != 'POST':
        return HttpResponse(status=405)

    try:
        payload = _json_body(request)
    except ValueError as exc:
        return HttpResponseBadRequest(str(exc))

    faculty_id = payload.get('faculty_id')
    if not faculty_id:
        return JsonResponse({'error': 'faculty_id is required.'}, status=400)

    with transaction.atomic():
        faculty = get_object_or_404(
            FacultyProfile.objects.select_for_update().select_related('user'),
            faculty_id=faculty_id,
        )
        if OfficeClosure.objects.filter(department=faculty.department_id, is_closed=True).exists():
            return JsonResponse({'error': 'This department is currently closed and not accepting walk-ins.'}, status=409)
        if not faculty.walk_ins_enabled:
            return JsonResponse({'error': 'This faculty member is not accepting walk-ins.'}, status=409)
        if not faculty.walk_ins_enabled:
            return JsonResponse({'error': 'This faculty member is not accepting walk-ins.'}, status=409)

        existing = WalkInQueue.objects.filter(
            faculty=faculty,
            user=request.user,
            status__in=['waiting', 'called'],
        ).first()
        if existing:
            return JsonResponse(_walk_in_json(existing), status=200)

        last_position = WalkInQueue.objects.filter(
            faculty=faculty,
            status__in=['waiting', 'called'],
        ).order_by('-position').values_list('position', flat=True).first() or 0
        queue = WalkInQueue.objects.create(
            queue_id=uuid.uuid4().hex,
            faculty=faculty,
            user=request.user,
            position=last_position + 1,
            joined_at=timezone.now(),
            student_message=str(payload.get('message') or '').strip(),
        )

    return JsonResponse(_walk_in_json(queue), status=201)
