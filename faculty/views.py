import json
from datetime import date, time

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
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
from .models import FacultyProfile, GoogleCalendarConnection, ScheduleEvent


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


def dashboard(request):
    return render(request, 'faculty/dashboardFaculty.html')


def booking_management(request):
    return render(request, 'faculty/bookingManagement.html')


def booking_management_legacy(request):
    return redirect('faculty:booking_management')


def profile(request):
    connection = None
    if request.user.is_authenticated:
        connection = GoogleCalendarConnection.objects.filter(user=request.user).first()
    return render(request, 'faculty/profile.html', {'calendar_connected': connection is not None})


def schedule(request):
    return render(request, 'faculty/scheduleFaculty.html')


@login_required
def calendar_connect(request):
    if request.method != 'GET':
        return HttpResponse(status=405)
    if _faculty_for_request(request) is None:
        return JsonResponse({'error': 'No faculty profile'}, status=400)
    try:
        return redirect(start_oauth(request))
    except GoogleCalendarError as exc:
        return JsonResponse({'error': str(exc)}, status=503)


@login_required
def calendar_callback(request):
    if request.GET.get('error'):
        return redirect('faculty:profile')
    code = request.GET.get('code')
    state = request.GET.get('state')
    if not code or not state:
        return HttpResponseBadRequest('Missing Google OAuth response')
    try:
        finish_oauth(request, code, state)
        sync_google_calendar(request.user)
    except (GoogleCalendarError, FacultyProfile.DoesNotExist):
        # Keep the connection so the user can retry sync later or reconnect.
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
        if GoogleCalendarConnection.objects.filter(user=request.user).exists():
            try:
                sync_google_calendar(request.user)
            except GoogleCalendarError as exc:
                sync_error = str(exc)

        events = ScheduleEvent.objects.filter(faculty=faculty).order_by('date', 'start_time')
        return JsonResponse({
            'events': [_event_json(event) for event in events],
            'calendar_connected': GoogleCalendarConnection.objects.filter(user=request.user).exists(),
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
