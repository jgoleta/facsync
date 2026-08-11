import json
import uuid
from datetime import date, time

from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import HttpResponse, HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_protect

from .facultyServices.googleCalendarService import (
    GoogleCalendarError,
    create_google_event,
    delete_google_event,
    disconnect_google_calendar,
    finish_oauth,
    start_oauth,
    sync_google_calendar,
    update_google_event,
)
from .models import FacultyProfile, GoogleCalendarConnection, ScheduleEvent, StatusHistory


def _faculty_for_request(request):
    if not request.user.is_authenticated:
        return None
    try:
        return request.user.faculty_profile
    except FacultyProfile.DoesNotExist:
        return None


def _json_body(request):
    try:
        payload = json.loads(request.body.decode('utf-8'))
    except (TypeError, ValueError, UnicodeDecodeError):
        raise ValueError('Invalid JSON')
    if not isinstance(payload, dict):
        raise ValueError('Invalid JSON')
    return payload


def _event_values(payload, existing=None):
    title = payload.get('title', existing.title if existing else '')
    if not title:
        raise ValueError('Missing title')

    date_value = payload.get('date', existing.date if existing else None)
    if isinstance(date_value, str):
        try:
            date_value = date.fromisoformat(date_value)
        except ValueError as exc:
            raise ValueError('Invalid date') from exc
    if not date_value:
        raise ValueError('Missing date')

    start_value = payload.get('start_time', existing.start_time if existing else None)
    end_value = payload.get('end_time', existing.end_time if existing else None)
    if isinstance(start_value, str) and start_value:
        try:
            start_value = time.fromisoformat(start_value)
        except ValueError as exc:
            raise ValueError('Invalid start time') from exc
    if isinstance(end_value, str) and end_value:
        try:
            end_value = time.fromisoformat(end_value)
        except ValueError as exc:
            raise ValueError('Invalid end time') from exc

    event_type = payload.get('event_type', existing.event_type if existing else 'busy')
    valid_types = {choice[0] for choice in ScheduleEvent.EVENT_TYPES}
    if event_type not in valid_types:
        raise ValueError('Invalid event type')

    return {
        'title': str(title)[:128],
        'description': payload.get('description', existing.description if existing else '') or '',
        'event_type': event_type,
        'date': date_value,
        'start_time': start_value or None,
        'end_time': end_value or None,
    }


def _event_json(event):
    return {
        'id': event.pk,
        'title': event.title,
        'description': event.description,
        'event_type': event.event_type,
        'date': event.date.isoformat(),
        'start_time': event.start_time.isoformat() if event.start_time else None,
        'end_time': event.end_time.isoformat() if event.end_time else None,
        'google_event_id': event.google_event_id,
    }


@login_required
def dashboard(request):
    faculty_profile = FacultyProfile.objects.filter(user=request.user).first()
    current_status = faculty_profile.current_status if faculty_profile else 'available'
    status_css_class = {
        'available': 'available',
        'busy': 'busy',
        'virtual_only': 'virtual',
        'on_leave': 'on-leave',
        'unavailable': 'unavailable',
    }.get(current_status, 'available')
    status_label = dict(FacultyProfile.STATUS_CHOICES).get(current_status, 'Available')
    return render(request, 'faculty/dashboardFaculty.html', {
        'faculty_profile': faculty_profile,
        'current_status': current_status,
        'status_css_class': status_css_class,
        'status_label': status_label,
    })


@login_required
@csrf_protect
def update_status(request):
    if request.method != 'POST':
        return HttpResponse(status=405)

    faculty_profile = FacultyProfile.objects.filter(user=request.user).first()
    if faculty_profile is None:
        return JsonResponse({'error': 'Faculty profile not found.'}, status=404)

    try:
        payload = _json_body(request)
    except ValueError as exc:
        return HttpResponseBadRequest(str(exc))

    submitted_status = payload.get('status')
    status_aliases = {'virtual': 'virtual_only', 'on-leave': 'on_leave'}
    status_css_classes = {
        'available': 'available',
        'busy': 'busy',
        'virtual_only': 'virtual',
        'on_leave': 'on-leave',
        'unavailable': 'unavailable',
    }
    status = status_aliases.get(submitted_status, submitted_status)
    valid_statuses = {choice[0] for choice in FacultyProfile.STATUS_CHOICES}
    if status not in valid_statuses:
        return JsonResponse({'error': 'Invalid faculty status.'}, status=400)

    previous_status = faculty_profile.current_status
    faculty_profile.current_status = status
    faculty_profile.status_note = str(payload.get('note') or '').strip()
    faculty_profile.status_updated_at = timezone.now()
    faculty_profile.save(update_fields=['current_status', 'status_note', 'status_updated_at'])

    if previous_status != status:
        StatusHistory.objects.create(
            history_id=uuid.uuid4().hex,
            faculty=faculty_profile,
            status=status,
            changed_at=faculty_profile.status_updated_at,
        )

    return JsonResponse({
        'status': status,
        'status_css_class': status_css_classes[status],
        'label': dict(FacultyProfile.STATUS_CHOICES)[status],
        'note': faculty_profile.status_note,
        'updated_at': faculty_profile.status_updated_at.isoformat(),
    })


@login_required
def booking_management(request):
    return render(request, 'faculty/bookingManagement.html')


def booking_management_legacy(request):
    return redirect('faculty:booking_management')


@login_required
@csrf_protect
def profile(request):
    connection = GoogleCalendarConnection.objects.filter(user=request.user).first()
    faculty_profile = FacultyProfile.objects.filter(user=request.user).first()

    if request.method == 'POST':
        if faculty_profile is None:
            return JsonResponse({'error': 'Faculty profile not found.'}, status=404)

        field = request.POST.get('field')
        if field == 'office_location':
            faculty_profile.office_location = request.POST.get('value', '').strip()[:128]
        elif field == 'biography':
            faculty_profile.biography = request.POST.get('value', '').strip()
        else:
            return JsonResponse({'error': 'Invalid profile field.'}, status=400)

        faculty_profile.save(update_fields=[field])
        return JsonResponse({'value': getattr(faculty_profile, field)})

    return render(request, 'faculty/profile.html', {
        'calendar_connected': connection is not None,
        'faculty_profile': faculty_profile,
    })


@login_required
def schedule(request):
    return render(request, 'faculty/scheduleFaculty.html')


@login_required
def calendar_connect(request):
    if request.method != 'GET':
        return HttpResponse(status=405)

    if request.GET.get('error'):
        messages.error(request, 'Google Calendar connection was cancelled or denied.')
        return redirect('faculty:profile')

    if request.GET.get('code'):
        code = request.GET.get('code')
        state = request.GET.get('state')
        if not state:
            messages.error(request, 'Google Calendar connection failed: missing OAuth state.')
            return redirect('faculty:profile')
        try:
            finish_oauth(request, code, state)
            sync_google_calendar(request.user)
        except (GoogleCalendarError, FacultyProfile.DoesNotExist) as exc:
            messages.error(request, f'Google Calendar connection failed: {exc}')
        else:
            messages.success(request, 'Google Calendar connected and synchronized successfully.')
        return redirect('faculty:profile')

    if _faculty_for_request(request) is None:
        return JsonResponse({'error': 'No faculty profile'}, status=400)
    try:
        return redirect(start_oauth(request))
    except GoogleCalendarError as exc:
        return JsonResponse({'error': str(exc)}, status=503)


@login_required
def calendar_callback(request):
    if request.GET.get('error'):
        messages.error(request, 'Google Calendar connection was cancelled or denied.')
        return redirect('faculty:profile')
    code = request.GET.get('code')
    state = request.GET.get('state')
    if not code or not state:
        return redirect('faculty:calendar_connect')
    try:
        finish_oauth(request, code, state)
        sync_google_calendar(request.user)
    except (GoogleCalendarError, FacultyProfile.DoesNotExist) as exc:
        messages.error(request, f'Google Calendar connection failed: {exc}')
        return redirect('faculty:profile')
    return redirect('faculty:profile')


@login_required
@csrf_protect
def calendar_disconnect(request):
    if request.method != 'POST':
        return HttpResponse(status=405)
    disconnect_google_calendar(request.user)
    return JsonResponse({'status': 'disconnected'})


@login_required
def calendar_status(request):
    connection = GoogleCalendarConnection.objects.filter(user=request.user).first()
    return JsonResponse({
        'connected': connection is not None,
        'last_synced_at': connection.last_synced_at.isoformat() if connection and connection.last_synced_at else None,
    })


@login_required
@csrf_protect
def api_schedule_events(request):
    faculty = _faculty_for_request(request)
    if faculty is None:
        return JsonResponse({'error': 'No faculty profile'}, status=400)

    if request.method == 'GET':
        sync_error = None
        sync_requested = request.GET.get('sync') == '1'
        calendar_connected = GoogleCalendarConnection.objects.filter(user=request.user).exists()
        if sync_requested and calendar_connected:
            try:
                sync_google_calendar(request.user)
            except GoogleCalendarError as exc:
                sync_error = str(exc)

        events = ScheduleEvent.objects.filter(faculty=faculty).order_by('date', 'start_time')
        return JsonResponse({
            'events': [_event_json(event) for event in events],
            'calendar_connected': calendar_connected,
            'sync_performed': sync_requested and calendar_connected,
            'sync_error': sync_error,
        })

    if request.method == 'POST':
        try:
            values = _event_values(_json_body(request))
        except ValueError as exc:
            return HttpResponseBadRequest(str(exc))

        event = ScheduleEvent(faculty=faculty, **values)
        connection = GoogleCalendarConnection.objects.filter(user=request.user).first()
        try:
            if connection:
                google_event = create_google_event(connection, event)
                event.google_event_id = google_event.get('id')
                event.google_calendar_id = connection.calendar_id
                if not event.google_event_id:
                    raise GoogleCalendarError('Google Calendar did not return an event ID.')
            event.save()
        except GoogleCalendarError as exc:
            return JsonResponse({'error': str(exc)}, status=502)
        return JsonResponse(_event_json(event), status=201)

    return HttpResponse(status=405)


@login_required
@csrf_protect
def api_schedule_event_detail(request, pk):
    faculty = _faculty_for_request(request)
    if faculty is None:
        return JsonResponse({'error': 'No faculty profile'}, status=400)
    event = get_object_or_404(ScheduleEvent, pk=pk, faculty=faculty)

    if request.method == 'GET':
        return JsonResponse(_event_json(event))

    connection = GoogleCalendarConnection.objects.filter(user=request.user).first()

    if request.method in ('PUT', 'PATCH'):
        try:
            values = _event_values(_json_body(request), existing=event)
        except ValueError as exc:
            return HttpResponseBadRequest(str(exc))
        for field, value in values.items():
            setattr(event, field, value)

        try:
            if connection:
                if event.google_event_id:
                    try:
                        update_google_event(connection, event)
                    except GoogleCalendarError as exc:
                        if '(404)' not in str(exc):
                            raise
                        google_event = create_google_event(connection, event)
                        event.google_event_id = google_event.get('id')
                        event.google_calendar_id = connection.calendar_id
                else:
                    google_event = create_google_event(connection, event)
                    event.google_event_id = google_event.get('id')
                    event.google_calendar_id = connection.calendar_id
                if not event.google_event_id:
                    raise GoogleCalendarError('Google Calendar did not return an event ID.')
            event.save()
        except GoogleCalendarError as exc:
            return JsonResponse({'error': str(exc)}, status=502)
        return JsonResponse(_event_json(event))

    if request.method == 'DELETE':
        try:
            if connection and event.google_event_id:
                delete_google_event(connection, event)
            event.delete()
        except GoogleCalendarError as exc:
            return JsonResponse({'error': str(exc)}, status=502)
        return JsonResponse({'status': 'deleted'})

    return HttpResponse(status=405)
