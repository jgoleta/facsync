from django.shortcuts import redirect, render, get_object_or_404
from django.http import JsonResponse, HttpResponseBadRequest, HttpResponse
from django.views.decorators.csrf import csrf_exempt
import json
from .models import ScheduleEvent, FacultyProfile


def dashboard(request):
    return render(request, 'faculty/dashboardFaculty.html')


def booking_management(request):
    return render(request, 'faculty/bookingManagement.html')


def booking_management_legacy(request):
    return redirect('faculty:booking_management')


def profile(request):
    return render(request, 'faculty/profile.html')


def schedule(request):
    return render(request, 'faculty/scheduleFaculty.html')


@csrf_exempt
def api_schedule_events(request):
    # List or create events for the logged-in faculty
    if request.method == 'GET':
        # If user is authenticated and has a faculty profile, filter by that
        faculty = None
        if request.user.is_authenticated:
            try:
                faculty = request.user.faculty_profile
            except FacultyProfile.DoesNotExist:
                faculty = None

        qs = ScheduleEvent.objects.all()
        if faculty is not None:
            qs = qs.filter(faculty=faculty)

        data = []
        for ev in qs.order_by('date', 'start_time'):
            data.append({
                'id': ev.pk,
                'title': ev.title,
                'description': ev.description,
                'event_type': ev.event_type,
                'date': ev.date.isoformat(),
                'start_time': ev.start_time.isoformat() if ev.start_time else None,
                'end_time': ev.end_time.isoformat() if ev.end_time else None,
            })
        return JsonResponse({'events': data})

    if request.method == 'POST':
        try:
            payload = json.loads(request.body.decode('utf-8'))
        except Exception:
            return HttpResponseBadRequest('Invalid JSON')

        # require faculty is the logged-in user's profile
        if not request.user.is_authenticated:
            return HttpResponse(status=401)
        try:
            faculty = request.user.faculty_profile
        except FacultyProfile.DoesNotExist:
            return HttpResponseBadRequest('No faculty profile')

        title = payload.get('title')
        description = payload.get('description', '')
        event_type = payload.get('event_type', 'busy')
        date = payload.get('date')
        start_time = payload.get('start_time')
        end_time = payload.get('end_time')

        if not title or not date:
            return HttpResponseBadRequest('Missing fields')

        ev = ScheduleEvent.objects.create(
            faculty=faculty,
            title=title,
            description=description,
            event_type=event_type,
            date=date,
            start_time=start_time or None,
            end_time=end_time or None,
        )

        return JsonResponse({'id': ev.pk}, status=201)

    return HttpResponseBadRequest('Unsupported method')


@csrf_exempt
def api_schedule_event_detail(request, pk):
    ev = get_object_or_404(ScheduleEvent, pk=pk)

    # Ensure only faculty owner can edit/delete
    if request.method == 'GET':
        return JsonResponse({
            'id': ev.pk,
            'title': ev.title,
            'description': ev.description,
            'event_type': ev.event_type,
            'date': ev.date.isoformat(),
            'start_time': ev.start_time.isoformat() if ev.start_time else None,
            'end_time': ev.end_time.isoformat() if ev.end_time else None,
        })

    if request.method in ('PUT', 'PATCH'):
        if not request.user.is_authenticated:
            return HttpResponse(status=401)
        try:
            faculty = request.user.faculty_profile
        except FacultyProfile.DoesNotExist:
            return HttpResponseBadRequest('No faculty profile')

        if ev.faculty != faculty:
            return HttpResponse(status=403)

        try:
            payload = json.loads(request.body.decode('utf-8'))
        except Exception:
            return HttpResponseBadRequest('Invalid JSON')

        ev.title = payload.get('title', ev.title)
        ev.description = payload.get('description', ev.description)
        ev.event_type = payload.get('event_type', ev.event_type)
        ev.date = payload.get('date', ev.date)
        ev.start_time = payload.get('start_time', ev.start_time)
        ev.end_time = payload.get('end_time', ev.end_time)
        ev.save()
        return JsonResponse({'status': 'ok'})

    if request.method == 'DELETE':
        if not request.user.is_authenticated:
            return HttpResponse(status=401)
        try:
            faculty = request.user.faculty_profile
        except FacultyProfile.DoesNotExist:
            return HttpResponseBadRequest('No faculty profile')
        if ev.faculty != faculty:
            return HttpResponse(status=403)
        ev.delete()
        return JsonResponse({'status': 'deleted'})

    return HttpResponseBadRequest('Unsupported method')
