import json
import uuid

from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpResponse, HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_protect

from faculty.models import FacultyProfile, StatusHistory, WalkInQueue
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


def _faculty_directory():
    directory = []
    for faculty in FacultyProfile.objects.select_related('user').all():
        refresh_faculty_status(faculty)
        directory.append({
            'faculty_id': faculty.faculty_id,
            'name': faculty.user.get_full_name() or faculty.user.username,
            'department': faculty.department_id,
            'status': faculty.current_status,
            'note': faculty.status_note,
            'walk_ins_enabled': faculty.walk_ins_enabled,
            'updated_at': faculty.status_updated_at.isoformat() if faculty.status_updated_at else None,
        })
    return directory

@login_required
def dashboard(request):
    faculty_statuses = FacultyProfile.objects.select_related('user').all()
    status_history = StatusHistory.objects.select_related('faculty__user').order_by('-changed_at')[:10]
    faculty_directory = _faculty_directory()
    return render(request, 'students/dashboardStudent.html', {
        'faculty_statuses': faculty_statuses,
        'status_history': status_history,
        'faculty_directory': faculty_directory,
    })

@login_required
def view_schedule(request):
    faculty = _faculty_for_schedule(request)
    if faculty:
        refresh_faculty_status(faculty)
    return render(request, 'students/viewSchedule.html', {
        'selected_faculty': faculty,
    })

def consultation_requests(request):
    return render(request, 'students/consultationRequests.html')

def home(request):
    return render(request, 'students/homeStudent.html')


@login_required
def api_faculty_statuses(request):
    """Return calendar-derived faculty statuses for live student dashboards."""
    if request.method != 'GET':
        return HttpResponse(status=405)
    return JsonResponse({'faculty': _faculty_directory()})


@login_required
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
