from .services.consultation_browser import QUESTIONS as FACULTY_BROWSER_QUESTIONS, consultation_browser_answer
from django.views.decorators.http import require_GET
import csv
import io
import json
import re
from datetime import date, datetime, time, timedelta

from django.contrib.auth.decorators import login_required
from apps.core.decorators import role_required
from django.db import transaction
from django.db.models import Count, Q
from django.contrib import messages
from django.core.mail import send_mail
from django.conf import settings
from django.http import HttpResponse, HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.cache import never_cache
from apps.core.models import CollegeAnnouncement
from apps.core.services import create_notification, get_active_announcements
from django.http import JsonResponse
from django.utils import timezone


from .services.google_calendar import (
    GoogleCalendarError,
    consultation_has_calendar_conflict,
    create_consultation_event,
    create_google_event,
    delete_consultation_event,
    delete_google_event,
    delete_google_event_instance,
    disconnect_google_calendar,
    finish_oauth,
    update_consultation_event,
    start_oauth,
    sync_google_calendar,
    refresh_faculty_status,
    update_google_event,
)
from .services.calendar_events import (
    get_schedule_status_label,
    serialize_consultation_event,
    serialize_schedule_event,
)
from .models import (
    ConsultationRequest,
    FacultyProfile,
    GoogleCalendarConnection,
    ScheduleEvent,
    WalkInQueue,
)


SCHEDULE_CSV_HEADERS = [
    'OFFERING_ID', 'SUBJ_CODE', 'SECTION', 'SUBJECT_TITLE', 'UNITS',
    'LECTURE', 'LAB', 'RECURRING_DAY', 'DAYFROM', 'DAYTO', 'TIMEFROM', 'TIMETO', 'ROOM',
]
LEGACY_SCHEDULE_CSV_HEADERS = [header for header in SCHEDULE_CSV_HEADERS if header != 'RECURRING_DAY']
OLDER_SCHEDULE_CSV_HEADERS = [
    'event_title', 'short_description', 'room_location', 'recurring_day',
    'start_month', 'end_month', 'start_time', 'end_time', 'status_type',
]
SCHEDULE_CSV_MAX_BYTES = 2 * 1024 * 1024
SCHEDULE_CSV_MAX_ROWS = 500
SCHEDULE_WEEKDAYS = {
    'monday': 'Monday',
    'tuesday': 'Tuesday',
    'wednesday': 'Wednesday',
    'thursday': 'Thursday',
    'friday': 'Friday',
    'saturday': 'Saturday',
    'sunday': 'Sunday',
}
SCHEDULE_MONTHS = set(range(1, 13))
SCHEDULE_STATUS_TYPES = {
    'busy': ('Busy', 'busy'),
    'available': ('Available', 'virtual'),
    'class': ('Class', 'busy'),
    'office hours': ('Office Hours', 'busy'),
    'unavailable': ('Unavailable', 'unavailable'),
    'on leave': ('On Leave', 'on-leave'),
}
SCHEDULE_TIME_RE = re.compile(r'^([01]\d|2[0-3]):([0-5]\d)$')
SCHEDULE_DATE_FORMATS = ('%Y-%m-%d', '%m/%d/%Y', '%m-%d-%Y', '%B %d, %Y', '%b %d, %Y')


def _parse_schedule_date(value):
    """Parse ISO and common spreadsheet date formats used in uploaded CSVs."""
    value = str(value or '').strip()
    for date_format in SCHEDULE_DATE_FORMATS:
        try:
            return datetime.strptime(value, date_format).date()
        except ValueError:
            continue
    raise ValueError(value)


def _faculty_for_request(request):
    """Return the signed-in user's faculty profile, if one exists."""
    if not request.user.is_authenticated:
        return None
    try:
        return request.user.faculty_profile
    except FacultyProfile.DoesNotExist:
        return None


def _json_body(request):
    """Decode a JSON request body and reject malformed or non-object payloads."""
    try:
        payload = json.loads(request.body.decode('utf-8'))
    except (TypeError, ValueError, UnicodeDecodeError):
        raise ValueError('Invalid JSON')
    if not isinstance(payload, dict):
        raise ValueError('Invalid JSON')
    return payload


def _event_values(payload, existing=None):
    """Validate and normalize schedule-event fields from an API payload."""
    title = payload.get('title', existing.title if existing else '')
    if not title:
        raise ValueError('Missing title')

    day_of_week = str(payload.get('day_of_week', existing.day_of_week if existing else '') or '').strip().casefold()
    if day_of_week == 'none':
        day_of_week = ''
    if day_of_week and day_of_week not in SCHEDULE_WEEKDAYS:
        raise ValueError('Invalid day of week')

    def parse_month(value, field_name):
        if value in (None, ''):
            return None
        try:
            month = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f'Invalid {field_name}') from exc
        if month not in SCHEDULE_MONTHS:
            raise ValueError(f'{field_name} must be between 1 and 12')
        return month

    start_month = parse_month(
        payload.get('start_month', existing.start_month if existing else None),
        'start month',
    )
    end_month = parse_month(
        payload.get('end_month', existing.end_month if existing else None),
        'end month',
    )
    allocation_start_date = payload.get('start_date')
    allocation_end_date = payload.get('end_date')
    if allocation_start_date or allocation_end_date:
        try:
            allocation_start_date = date.fromisoformat(str(allocation_start_date))
            allocation_end_date = date.fromisoformat(str(allocation_end_date))
        except (TypeError, ValueError) as exc:
            raise ValueError('Invalid allocation start or end date') from exc
        if allocation_start_date > allocation_end_date:
            raise ValueError('Allocation start date must be on or before the end date')
        start_month = allocation_start_date.month
        end_month = allocation_end_date.month
    elif existing:
        allocation_start_date = existing.recurrence_start_date
        allocation_end_date = existing.recurrence_end_date
    recurring = (
        (
            'day_of_week' in payload
            and (bool(day_of_week) or payload.get('date') in (None, ''))
        )
        or payload.get('start_month') not in (None, '')
        or payload.get('end_month') not in (None, '')
        or bool(existing and (existing.date is None or existing.start_month or existing.end_month))
    )
    if recurring and day_of_week and (start_month is None or end_month is None):
        raise ValueError('Recurring schedules require a start month and end month')

    date_value = payload.get('date', existing.date if existing else None)
    if recurring:
        date_value = None
    if isinstance(date_value, str):
        try:
            date_value = date.fromisoformat(date_value)
        except ValueError as exc:
            raise ValueError('Invalid date') from exc
    # A None recurring day is a valid time-only schedule. Date-based events
    # still require an exact date when they are not marked recurring.
    if not date_value and not day_of_week and not recurring:
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
    if start_value and end_value and start_value >= end_value:
        raise ValueError('Start time must be earlier than end time')

    event_type = payload.get('event_type', existing.event_type if existing else 'busy')
    valid_types = {choice[0] for choice in ScheduleEvent.EVENT_TYPES}
    if event_type not in valid_types:
        raise ValueError('Invalid event type')

    if 'status' in payload:
        schedule_status = payload.get('status')
    elif existing and existing.schedule_status and event_type == existing.event_type:
        schedule_status = existing.schedule_status
    else:
        schedule_status = dict(ScheduleEvent.EVENT_TYPES).get(event_type, event_type)

    return {
        'title': str(title)[:128],
        'description': payload.get('description', existing.description if existing else '') or '',
        'location': str(payload.get('location', existing.location if existing else '') or '').strip()[:128],
        'schedule_status': str(schedule_status or '').strip()[:32],
        'event_type': event_type,
        'date': date_value,
        'day_of_week': day_of_week,
        'start_month': start_month if recurring else None,
        'end_month': end_month if recurring else None,
        'recurrence_start_date': allocation_start_date if recurring else None,
        'recurrence_end_date': allocation_end_date if recurring else None,
        'start_time': start_value or None,
        'end_time': end_value or None,
    }


def _event_json(event):
    return serialize_schedule_event(event, include_sync_metadata=True, human_status=True)


def _adjust_recurring_edit(event, values):
    """Carry occurrence exclusions and the final boundary to a new weekday."""
    old_day = event.day_of_week
    new_day = values.get('day_of_week')
    if event.date is not None or not old_day or not new_day or old_day == new_day:
        return

    weekday_indexes = {day: index for index, day in enumerate(SCHEDULE_WEEKDAYS)}
    old_index = weekday_indexes[old_day]
    new_index = weekday_indexes[new_day]

    translated_exclusions = []
    for value in event.recurrence_excluded_dates or []:
        try:
            excluded_date = date.fromisoformat(value)
        except (TypeError, ValueError):
            translated_exclusions.append(value)
            continue
        if excluded_date.weekday() == old_index:
            week_start = excluded_date - timedelta(days=excluded_date.weekday())
            excluded_date = week_start + timedelta(days=new_index)
        translated_exclusions.append(excluded_date.isoformat())
    event.recurrence_excluded_dates = translated_exclusions

    end_date = values.get('recurrence_end_date')
    if end_date:
        last_old_occurrence = end_date - timedelta(
            days=(end_date.weekday() - old_index) % 7,
        )
        week_start = last_old_occurrence - timedelta(days=last_old_occurrence.weekday())
        last_new_occurrence = week_start + timedelta(days=new_index)
        if last_new_occurrence > end_date:
            values['recurrence_end_date'] = last_new_occurrence
            values['end_month'] = last_new_occurrence.month


def _consultation_event_json(consultation):
    return serialize_consultation_event(consultation, viewer='faculty')


def _csv_error(row_number, message):
    """Format a validation message consistently for the upload UI/API."""
    return f'Row {row_number}: {message}'


def _parse_schedule_csv(uploaded_file):
    """Parse and validate a complete schedule CSV before anything is saved."""
    if not uploaded_file or not getattr(uploaded_file, 'name', '').lower().endswith('.csv'):
        raise ValueError('Please upload a CSV file with a .csv extension.')
    if uploaded_file.size == 0:
        raise ValueError('The CSV file is empty.')
    if uploaded_file.size > SCHEDULE_CSV_MAX_BYTES:
        raise ValueError('The CSV file is too large. The maximum size is 2 MB.')

    try:
        content = uploaded_file.read().decode('utf-8-sig')
    except UnicodeDecodeError as exc:
        raise ValueError('The CSV file must use UTF-8 encoding.') from exc

    try:
        reader = csv.DictReader(io.StringIO(content, newline=''), strict=True)
        headers = reader.fieldnames
        csv_rows = list(reader)
    except csv.Error as exc:
        raise ValueError(f'Unable to read the CSV file: {exc}') from exc
    if headers == OLDER_SCHEDULE_CSV_HEADERS:
        return _parse_older_schedule_csv(csv_rows)
    if headers not in (SCHEDULE_CSV_HEADERS, LEGACY_SCHEDULE_CSV_HEADERS):
        expected = ', '.join(SCHEDULE_CSV_HEADERS)
        actual = ', '.join(headers or []) or 'none'
        raise ValueError(f'Invalid CSV headers. Expected: {expected}. Found: {actual}.')

    parsed = []
    errors = []
    intervals_by_day = {}
    offering_ids = set()
    for row_number, row in enumerate(csv_rows, start=2):
        if None in row and any(str(value or '').strip() for value in row[None]):
            errors.append(_csv_error(row_number, 'The row contains more values than the thirteen required columns.'))
            continue
        if row is None or all(not str(value or '').strip() for value in row.values() if value is not None):
            continue
        if row_number - 1 > SCHEDULE_CSV_MAX_ROWS:
            errors.append(_csv_error(row_number, f'File exceeds the {SCHEDULE_CSV_MAX_ROWS}-row limit.'))
            break

        values = {key: (value or '').strip() for key, value in row.items() if key in SCHEDULE_CSV_HEADERS}
        values.setdefault('RECURRING_DAY', '')
        required_headers = LEGACY_SCHEDULE_CSV_HEADERS if headers == LEGACY_SCHEDULE_CSV_HEADERS else SCHEDULE_CSV_HEADERS
        missing = [key for key in required_headers if key != 'ROOM' and not values.get(key)]
        if missing:
            errors.append(_csv_error(row_number, f'Missing required value(s): {", ".join(missing)}.'))
            continue
        if values['OFFERING_ID'] in offering_ids:
            errors.append(_csv_error(row_number, 'OFFERING_ID must be unique within the CSV file.'))
            continue
        offering_ids.add(values['OFFERING_ID'])

        try:
            day_from = _parse_schedule_date(values['DAYFROM'])
            day_to = _parse_schedule_date(values['DAYTO'])
            if day_from > day_to:
                errors.append(_csv_error(row_number, 'DAYFROM must be on or before DAYTO.'))
                continue
            day_key = values['RECURRING_DAY'].casefold()
            if day_key and day_key not in SCHEDULE_WEEKDAYS:
                errors.append(_csv_error(row_number, 'RECURRING_DAY must be a valid weekday.'))
                continue
            day_label = f'{day_from.isoformat()} to {day_to.isoformat()}'
        except ValueError:
            errors.append(_csv_error(row_number, 'DAYFROM and DAYTO must use YYYY-MM-DD, MM/DD/YYYY, or MM-DD-YYYY dates.'))
            continue
        except KeyError:
            errors.append(_csv_error(row_number, 'DAYFROM and DAYTO are required and must use ISO dates (YYYY-MM-DD).'))
            continue

        start_match = SCHEDULE_TIME_RE.fullmatch(values['TIMEFROM'])
        end_match = SCHEDULE_TIME_RE.fullmatch(values['TIMETO'])
        if not start_match or not end_match:
            errors.append(_csv_error(row_number, 'TIMEFROM and TIMETO must use 24-hour HH:MM format.'))
            continue
        start_value = time.fromisoformat(values['TIMEFROM'])
        end_value = time.fromisoformat(values['TIMETO'])
        if start_value >= end_value:
            errors.append(_csv_error(row_number, 'TIMEFROM must be earlier than TIMETO.'))
            continue

        if len(values['ROOM']) > 128:
            errors.append(_csv_error(row_number, 'ROOM must be 128 characters or fewer.'))
            continue

        interval = (start_value, end_value, row_number)
        interval_key = (day_key, day_from, day_to)
        intervals_by_day.setdefault(interval_key, []).append(interval)
        parsed.append({
            'day': day_label,
            'date': None if day_key else day_from,
            'start_month': day_from.month if day_key else None,
            'end_month': day_to.month if day_key else None,
            'recurrence_start_date': day_from,
            'recurrence_end_date': day_to,
            'day_of_week': day_key,
            'offering_id': values['OFFERING_ID'],
            'subject_code': values['SUBJ_CODE'],
            'section': values['SECTION'],
            'title': values['SUBJECT_TITLE'],
            'units': values['UNITS'],
            'lecture': values['LECTURE'],
            'lab': values['LAB'],
            'recurring_day': values['RECURRING_DAY'],
            'description': f"{values['SUBJ_CODE']} {values['SECTION']}".strip(),
            'start_time': start_value,
            'end_time': end_value,
            'status': 'Class',
            'event_type': 'busy',
            'room': values['ROOM'],
        })

    for (day, day_from, day_to), intervals in intervals_by_day.items():
        ordered = sorted(intervals)
        for previous, current in zip(ordered, ordered[1:]):
            if current[0] < previous[1]:
                errors.append(_csv_error(
                    current[2],
                    f'Overlaps the {SCHEDULE_WEEKDAYS.get(day, "date-based")} time slot from '
                    f'{previous[0].strftime("%H:%M")} to {previous[1].strftime("%H:%M")}.',
                ))

    if not parsed and not errors:
        errors.append('The CSV contains no schedule rows.')
    if errors:
        raise ValueError(errors)
    return parsed


def _parse_older_schedule_csv(csv_rows):
    """Accept the original compact schedule CSV format for existing files."""
    parsed = []
    errors = []
    intervals_by_day = {}
    for row_number, row in enumerate(csv_rows, start=2):
        if row is None or all(not str(value or '').strip() for value in row.values() if value is not None):
            continue
        values = {key: (value or '').strip() for key, value in row.items()}
        missing = [key for key in OLDER_SCHEDULE_CSV_HEADERS if key != 'room_location' and not values.get(key)]
        if missing:
            errors.append(_csv_error(row_number, f'Missing required value(s): {", ".join(missing)}.'))
            continue
        day_key = values['recurring_day'].casefold()
        if day_key not in SCHEDULE_WEEKDAYS:
            errors.append(_csv_error(row_number, 'recurring_day must be a valid weekday.'))
            continue
        try:
            start_month = int(values['start_month'])
            end_month = int(values['end_month'])
        except ValueError:
            errors.append(_csv_error(row_number, 'start_month and end_month must be numbers from 1 to 12.'))
            continue
        if start_month not in SCHEDULE_MONTHS or end_month not in SCHEDULE_MONTHS:
            errors.append(_csv_error(row_number, 'start_month and end_month must be between 1 and 12.'))
            continue
        start_match = SCHEDULE_TIME_RE.fullmatch(values['start_time'])
        end_match = SCHEDULE_TIME_RE.fullmatch(values['end_time'])
        if not start_match or not end_match:
            errors.append(_csv_error(row_number, 'start_time and end_time must use 24-hour HH:MM format.'))
            continue
        start_value = time.fromisoformat(values['start_time'])
        end_value = time.fromisoformat(values['end_time'])
        if start_value >= end_value:
            errors.append(_csv_error(row_number, 'start_time must be earlier than end_time.'))
            continue
        status_key = values['status_type'].casefold()
        status_label, event_type = SCHEDULE_STATUS_TYPES.get(status_key, (None, None))
        if status_label is None:
            errors.append(_csv_error(row_number, 'status_type is not recognized.'))
            continue
        interval = (start_value, end_value, row_number)
        intervals_by_day.setdefault(day_key, []).append(interval)
        parsed.append({
            'day': SCHEDULE_WEEKDAYS[day_key],
            'date': None,
            'start_month': start_month,
            'end_month': end_month,
            'recurrence_start_date': None,
            'recurrence_end_date': None,
            'day_of_week': day_key,
            'offering_id': f'LEGACY-{row_number}',
            'subject_code': '',
            'section': '',
            'title': values['event_title'][:128],
            'units': '',
            'lecture': '',
            'lab': '',
            'description': values['short_description'],
            'start_time': start_value,
            'end_time': end_value,
            'status': status_label,
            'event_type': event_type,
            'room': values['room_location'][:128],
        })
    for day, intervals in intervals_by_day.items():
        ordered = sorted(intervals)
        for previous, current in zip(ordered, ordered[1:]):
            if current[0] < previous[1]:
                errors.append(_csv_error(
                    current[2],
                    f'Overlaps the {SCHEDULE_WEEKDAYS[day]} time slot from '
                    f'{previous[0].strftime("%H:%M")} to {previous[1].strftime("%H:%M")}.',
                ))
    if not parsed and not errors:
        errors.append('The CSV contains no schedule rows.')
    if errors:
        raise ValueError(errors)
    return parsed


def _schedule_csv_row(event):
    return {
        'OFFERING_ID': event.offering_id,
        'SUBJ_CODE': event.subject_code,
        'SECTION': event.section,
        'SUBJECT_TITLE': event.title,
        'UNITS': event.units,
        'LECTURE': event.lecture,
        'LAB': event.lab,
        'RECURRING_DAY': event.day_of_week,
        'DAYFROM': event.recurrence_start_date.isoformat() if event.recurrence_start_date else (event.date.isoformat() if event.date else ''),
        'DAYTO': event.recurrence_end_date.isoformat() if event.recurrence_end_date else (event.date.isoformat() if event.date else ''),
        'TIMEFROM': event.start_time.strftime('%H:%M') if event.start_time else '',
        'TIMETO': event.end_time.strftime('%H:%M') if event.end_time else '',
        'ROOM': event.location,
    }


@login_required
@role_required('faculty')
@never_cache
def dashboard(request):
    """Render the faculty dashboard with the current status presentation."""
    faculty_profile = FacultyProfile.objects.filter(user=request.user).first()
    if faculty_profile:
        refresh_faculty_status(faculty_profile)
    faculty_consultations = ConsultationRequest.objects.filter(faculty=faculty_profile) if faculty_profile else ConsultationRequest.objects.none()
    consultation_requests = faculty_consultations.exclude(
        status__in={'completed', 'declined', 'cancelled'},
    ).select_related('user').order_by('-date', '-start_time')
    completed_consultations = faculty_consultations.filter(
        status='completed',
    ).select_related('user').order_by('-date', '-start_time')
    today = timezone.localdate()
    consultation_counts = faculty_consultations.aggregate(
        pending=Count('request_id', filter=Q(status='pending')),
        approved=Count('request_id', filter=Q(status__in=['approved', 'cancellation_requested'])),
        today=Count('request_id', filter=Q(date=today) & ~Q(status__in=['declined', 'cancelled'])),
    )
    current_status = faculty_profile.current_status if faculty_profile else 'not_set'
    status_css_class = {
        'not_set': 'not-set',
        'available': 'available',
        'busy': 'busy',
        'virtual_only': 'virtual',
        'on_leave': 'on-leave',
        'unavailable': 'unavailable',
    }.get(current_status, 'not-set')
    status_label = dict(FacultyProfile.STATUS_CHOICES).get(current_status, 'Not Set')
    announcement_cutoff = timezone.now()
    college_announcements = CollegeAnnouncement.objects.filter(
        college__iexact=request.user.college,
        audience__in=('faculty', 'both'),
    )
    announcements = []
    past_announcements = []
    for announcement in college_announcements:
        if announcement.expiry <= announcement_cutoff:
            past_announcements.append(announcement)
        elif request.user.college:
            announcements.append({
                'college': announcement.get_college_display(),
                'message': announcement.message,
                'posted_at': announcement.posted_at.strftime('%b %d, %Y'),
            })

    return render(request, 'faculty/dashboardFaculty.html', {
        'analytics_questions': [{'metric': key, 'group': group, 'question': question} for key, (group, question) in FACULTY_BROWSER_QUESTIONS.items()],
        'faculty_profile': faculty_profile,
        'current_status': current_status,
        'manual_status_override': faculty_profile.manual_status_override if faculty_profile else False,
        'manual_status_expires_at': faculty_profile.manual_status_expires_at.isoformat() if faculty_profile and faculty_profile.manual_status_expires_at else '',
        'status_css_class': status_css_class,
        'status_label': status_label,
        'consultation_requests': consultation_requests,
        'completed_consultations': completed_consultations,
        'pending_consultation_count': consultation_counts['pending'],
        'approved_consultation_count': consultation_counts['approved'],
        'consultations_today_count': consultation_counts['today'],
        'announcements': announcements,
        'past_announcements': past_announcements,
    })


@login_required
@role_required('faculty')
def active_announcements(request):
    return JsonResponse({'announcements': get_active_announcements(request.user.college, audience='faculty')})


@login_required
@role_required('faculty')
@csrf_protect
@transaction.atomic
def update_status(request):
    """Save a faculty member's manual status and append a status-history record."""
    if request.method != 'POST':
        return HttpResponse(status=405)

    faculty_profile = FacultyProfile.objects.select_for_update().filter(user=request.user).first()
    if faculty_profile is None:
        return JsonResponse({'error': 'Faculty profile not found.'}, status=404)

    try:
        payload = _json_body(request)
    except ValueError as exc:
        return HttpResponseBadRequest(str(exc))

    submitted_status = payload.get('status', faculty_profile.manual_status)
    status_aliases = {'virtual': 'virtual_only', 'on-leave': 'on_leave'}
    status_css_classes = {
        'not_set': 'not-set',
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

    faculty_profile.manual_status = status
    manual_override = payload.get('manual_override', True)
    if not isinstance(manual_override, bool):
        return JsonResponse({'error': 'manual_override must be true or false.'}, status=400)
    faculty_profile.manual_status_override = manual_override
    expires_at = None
    submitted_expiry = payload.get('expires_at')
    if manual_override and submitted_expiry:
        expires_at = parse_datetime(str(submitted_expiry))
        if expires_at is None or timezone.is_naive(expires_at):
            return JsonResponse({'error': 'expires_at must be a valid date and time with a time zone.'}, status=400)
        if expires_at <= timezone.now():
            return JsonResponse({'error': 'The status end time must be in the future.'}, status=400)
    faculty_profile.manual_status_expires_at = expires_at
    faculty_profile.status_note = str(payload.get('note') or '').strip()
    faculty_profile.save(update_fields=[
        'manual_status', 'manual_status_override', 'manual_status_expires_at', 'status_note',
    ])
    effective_status = refresh_faculty_status(faculty_profile, immediate_email=True)
    faculty_profile.refresh_from_db()

    return JsonResponse({
        'status': effective_status,
        'status_css_class': status_css_classes[effective_status],
        'label': dict(FacultyProfile.STATUS_CHOICES)[effective_status],
        'note': faculty_profile.status_note,
        'manual_override': faculty_profile.manual_status_override,
        'expires_at': faculty_profile.manual_status_expires_at.isoformat() if faculty_profile.manual_status_expires_at else None,
        'updated_at': faculty_profile.status_updated_at.isoformat() if faculty_profile.status_updated_at else None,
    })


@login_required
@role_required('faculty')
def booking_management(request):
    """Render the faculty booking-management page."""
    faculty_profile = FacultyProfile.objects.filter(user=request.user).first()
    return render(request, 'faculty/bookingManagement.html', {
        'faculty_profile': faculty_profile,
    })


def booking_management_legacy(request):
    """Redirect the legacy booking URL to the current booking page."""
    return redirect('faculty:booking_management')


@login_required
@role_required('faculty')
@csrf_protect
def profile(request):
    """Render or update the faculty profile and Google Calendar integration settings."""
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
        'calendar_sync_enabled': bool(faculty_profile and faculty_profile.sync_enabled),
        'calendar_last_synced_at': connection.last_synced_at if connection else None,
        'calendar_sync_error': connection.last_sync_error if connection else '',
        'faculty_profile': faculty_profile,
    })


@login_required
@role_required('faculty')
def schedule(request):
    """Render the faculty schedule page."""
    faculty_profile = _faculty_for_request(request)
    if faculty_profile:
        refresh_faculty_status(faculty_profile)
    return render(request, 'faculty/scheduleFaculty.html', {
        'faculty_profile': faculty_profile,
    })


@login_required
@role_required('faculty')
def schedule_template(request):
    """Download the canonical UTF-8 schedule CSV template."""
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename=schedule_template.csv'
    writer = csv.writer(response)
    writer.writerow(SCHEDULE_CSV_HEADERS)
    writer.writerow(['OFFERING-001', 'CS101', 'A', 'Introduction to Computing', '3', '3', '0', 'Monday', '2026-08-17', '2026-12-15', '10:30', '12:00', 'Room 204'])
    writer.writerow(['OFFERING-002', 'CS102', 'A', 'Data Structures', '3', '3', '0', 'Tuesday', '2026-08-18', '2026-12-15', '13:00', '15:00', 'Room 204'])
    return response


@login_required
@role_required('faculty')
@csrf_protect
def upload_schedule(request):
    """Validate and atomically append rows to the signed-in faculty member's schedule."""
    if request.method != 'POST':
        return HttpResponse(status=405)
    faculty = _faculty_for_request(request)
    if faculty is None:
        return JsonResponse({'error': 'No faculty profile'}, status=400)
    uploaded_file = request.FILES.get('file')
    try:
        rows = _parse_schedule_csv(uploaded_file)
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
                offering_id=row['offering_id'],
                subject_code=row['subject_code'],
                section=row['section'],
                units=row['units'],
                lecture=row['lecture'],
                lab=row['lab'],
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
            for row in rows
        ])
        faculty.schedule_last_updated_at = updated_at
        faculty.save(update_fields=['schedule_last_updated_at'])

    calendar_sync = {
        'requested': request.POST.get('sync_to_google') == 'true',
        'status': 'not_requested',
        'synced_count': 0,
        'failed_count': 0,
    }
    if calendar_sync['requested']:
        connection = GoogleCalendarConnection.objects.filter(user=request.user).first()
        if connection is None:
            calendar_sync.update(
                status='not_connected',
                message='Connect Google Calendar before syncing this schedule.',
            )
        elif not faculty.sync_enabled:
            calendar_sync.update(
                status='disabled',
                message='Google Calendar sync is disabled in your profile.',
            )
        else:
            for event in events:
                try:
                    google_event = create_google_event(connection, event)
                    event.google_event_id = google_event.get('id')
                    event.google_calendar_id = connection.calendar_id
                    event.sync_state = 'synced'
                    event.sync_error = ''
                    if not event.google_event_id:
                        raise GoogleCalendarError('Google Calendar did not return an event ID.')
                    event.save(update_fields=[
                        'google_event_id', 'google_calendar_id', 'sync_state', 'sync_error',
                        'updated_at',
                    ])
                    calendar_sync['synced_count'] += 1
                except GoogleCalendarError as exc:
                    event.sync_state = 'out_of_sync'
                    event.sync_error = str(exc)
                    event.save(update_fields=['sync_state', 'sync_error', 'updated_at'])
                    calendar_sync['failed_count'] += 1
            calendar_sync['status'] = (
                'synced' if not calendar_sync['failed_count'] else 'partial'
            )
            if calendar_sync['failed_count']:
                calendar_sync['message'] = (
                    f"{calendar_sync['synced_count']} event(s) synced; "
                    f"{calendar_sync['failed_count']} event(s) could not be synced."
                )

    return JsonResponse({
        'message': (
            f'Schedule uploaded successfully. {len(events)} row(s) added.'
            + (f" {calendar_sync['message']}" if calendar_sync.get('message') else '')
        ),
        'added_count': len(events),
        'calendar_sync': calendar_sync,
        'last_updated_at': updated_at.isoformat(),
        'preview': [_schedule_csv_row(event) for event in events],
        'events': [_event_json(event) for event in events],
    }, status=201)


@login_required
@role_required('faculty')
def view_schedule_preview(request):
    """Return the signed-in faculty member's unified uploaded schedule."""
    if request.method != 'GET':
        return HttpResponse(status=405)
    faculty = _faculty_for_request(request)
    if faculty is None:
        return JsonResponse({'error': 'No faculty profile'}, status=400)
    events = ScheduleEvent.objects.filter(
        faculty=faculty, is_csv_upload=True,
    ).select_related('uploaded_by').order_by('id')
    rows = []
    for event in events:
        uploader = event.uploaded_by
        label = 'Uploader unknown'
        if uploader is not None:
            label = ('Uploaded by you' if uploader.pk == request.user.pk
                     else f'Uploaded by {uploader.get_full_name() or uploader.username}')
        rows.append({
            **_schedule_csv_row(event),
            'id': event.pk,
            'uploader_label': label,
            'uploaded_by_other': uploader is not None and uploader.pk != request.user.pk,
        })
    return JsonResponse({'preview': rows})


@login_required
@role_required('faculty')
@csrf_protect
def clear_schedule(request):
    """Delete only the uploaded rows represented by the current preview."""
    if request.method != 'POST':
        return HttpResponse(status=405)
    faculty = _faculty_for_request(request)
    if faculty is None:
        return JsonResponse({'error': 'No faculty profile'}, status=400)

    try:
        payload = _json_body(request)
    except ValueError as exc:
        return HttpResponseBadRequest(str(exc))
    event_ids = payload.get('event_ids')
    if not isinstance(event_ids, list) or not event_ids:
        return JsonResponse({'error': 'No uploaded preview rows were selected for deletion.'}, status=400)
    try:
        event_ids = [int(event_id) for event_id in event_ids]
    except (TypeError, ValueError):
        return JsonResponse({'error': 'Invalid uploaded preview row IDs.'}, status=400)

    events = list(ScheduleEvent.objects.filter(
        faculty=faculty,
        pk__in=event_ids,
        is_csv_upload=True,
    ))
    connection = GoogleCalendarConnection.objects.filter(user=request.user).first()
    try:
        if connection:
            for event in events:
                if event.google_event_id:
                    delete_google_event(connection, event)
    except GoogleCalendarError as exc:
        return JsonResponse({'error': str(exc)}, status=502)

    with transaction.atomic():
        deleted_count, _ = ScheduleEvent.objects.filter(
            pk__in=[event.pk for event in events],
        ).delete()
        faculty.schedule_last_updated_at = timezone.now()
        faculty.save(update_fields=['schedule_last_updated_at'])
    return JsonResponse({'status': 'deleted', 'deleted_count': deleted_count})


def _walk_in_json(queue):
    """Serialize a walk-in queue entry for faculty and student clients."""
    return {
        'queue_id': queue.queue_id,
        'faculty_id': queue.faculty.faculty_id,
        'student_name': queue.user.get_full_name() or queue.user.username,
        'student_email': queue.user.email,
        # Send the readable college name instead of an internal code.
        'student_college': queue.user.college_name,
        'status': queue.status,
        'position': queue.position,
        'student_message': queue.student_message,
        'faculty_note': queue.faculty_note,
        'joined_at': queue.joined_at.isoformat(),
        'notified_at': queue.notified_at.isoformat() if queue.notified_at else None,
        'served_at': queue.served_at.isoformat() if queue.served_at else None,
    }


@login_required
@role_required('faculty')
@csrf_protect
def api_walk_in_preference(request):
    """Read or update the signed-in faculty member's walk-in availability."""
    faculty = _faculty_for_request(request)
    if faculty is None:
        return JsonResponse({'error': 'Faculty profile not found.'}, status=404)

    if request.method == 'GET':
        return JsonResponse({'walk_ins_enabled': faculty.walk_ins_enabled})
    if request.method != 'POST':
        return HttpResponse(status=405)

    try:
        payload = _json_body(request)
    except ValueError as exc:
        return HttpResponseBadRequest(str(exc))

    enabled = payload.get('enabled')
    if not isinstance(enabled, bool):
        return JsonResponse({'error': 'enabled must be true or false.'}, status=400)

    faculty.walk_ins_enabled = enabled
    faculty.save(update_fields=['walk_ins_enabled'])
    return JsonResponse({'walk_ins_enabled': faculty.walk_ins_enabled})


@login_required
@role_required('faculty')
def api_faculty_walk_ins(request):
    """List the signed-in faculty member's active walk-in queue."""
    if request.method != 'GET':
        return HttpResponse(status=405)

    faculty = _faculty_for_request(request)
    if faculty is None:
        return JsonResponse({'error': 'Faculty profile not found.'}, status=404)

    queues = WalkInQueue.objects.filter(
        faculty=faculty,
        status__in=['waiting', 'called'],
    ).select_related('user', 'faculty')
    return JsonResponse({
        'walk_ins_enabled': faculty.walk_ins_enabled,
        'queue': [_walk_in_json(queue) for queue in queues],
    })


@login_required
@csrf_protect
def api_walk_in_detail(request, queue_id):
    """Allow a faculty member to manage a queue entry or a student to cancel it."""
    queue = get_object_or_404(
        WalkInQueue.objects.select_related('faculty', 'faculty__user', 'user'),
        queue_id=queue_id,
    )
    faculty = _faculty_for_request(request)
    is_faculty = faculty is not None and queue.faculty_id == faculty.faculty_id
    is_student = queue.user_id == request.user.id
    if not is_faculty and not is_student:
        return JsonResponse({'error': 'You cannot modify this queue entry.'}, status=403)

    if request.method == 'GET':
        return JsonResponse(_walk_in_json(queue))
    if request.method != 'POST':
        return HttpResponse(status=405)

    try:
        payload = _json_body(request)
    except ValueError as exc:
        return HttpResponseBadRequest(str(exc))
    action = payload.get('action')

    if action == 'cancel' and is_student:
        if queue.status not in ['waiting', 'called']:
            return JsonResponse({'error': 'This queue entry is no longer active.'}, status=409)
        queue.status = 'cancelled'
        queue.save(update_fields=['status'])
        return JsonResponse(_walk_in_json(queue))

    if not is_faculty:
        return JsonResponse({'error': 'Only the faculty member can manage this queue entry.'}, status=403)

    if action == 'notify':
        if queue.status not in ['waiting', 'called']:
            return JsonResponse({'error': 'This queue entry is no longer active.'}, status=409)
        queue.status = 'called'
        queue.notified_at = queue.notified_at or timezone.now()
        queue.faculty_note = str(payload.get('faculty_note') or queue.faculty_note or '').strip()
        queue.save(update_fields=['status', 'notified_at', 'faculty_note'])
        if queue.user.email:
            send_mail(
                'Please enter the faculty office',
                f'{queue.faculty} is ready to see you. Please enter the office now.',
                settings.DEFAULT_FROM_EMAIL,
                [queue.user.email],
                fail_silently=True,
            )
        return JsonResponse(_walk_in_json(queue))

    if action == 'complete':
        if queue.status not in ['waiting', 'called']:
            return JsonResponse({'error': 'This queue entry is no longer active.'}, status=409)
        queue.status = 'completed'
        queue.served_at = timezone.now()
        queue.faculty_note = str(payload.get('faculty_note') or queue.faculty_note or '').strip()
        queue.save(update_fields=['status', 'served_at', 'faculty_note'])
        return JsonResponse(_walk_in_json(queue))

    if action == 'remove':
        # Cancel rather than delete so the queue history remains available.
        if queue.status not in ['waiting', 'called']:
            return JsonResponse({'error': 'This queue entry is no longer active.'}, status=409)
        queue.status = 'cancelled'
        queue.save(update_fields=['status'])
        return JsonResponse(_walk_in_json(queue))

    return JsonResponse({'error': 'Invalid queue action.'}, status=400)


@login_required
@role_required('faculty')
def calendar_connect(request):
    """Start OAuth or finish the legacy Google Calendar OAuth callback."""
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
            faculty = _faculty_for_request(request)
            if faculty:
                faculty.sync_enabled = True
                faculty.save(update_fields=['sync_enabled'])
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
@role_required('faculty')
def calendar_callback(request):
    """Finish the dedicated Google Calendar OAuth callback flow."""
    if request.GET.get('error'):
        messages.error(request, 'Google Calendar connection was cancelled or denied.')
        return redirect('faculty:profile')
    code = request.GET.get('code')
    state = request.GET.get('state')
    if not code or not state:
        return redirect('faculty:calendar_connect')
    try:
        finish_oauth(request, code, state)
        faculty = _faculty_for_request(request)
        if faculty:
            faculty.sync_enabled = True
            faculty.save(update_fields=['sync_enabled'])
        sync_google_calendar(request.user)
    except (GoogleCalendarError, FacultyProfile.DoesNotExist) as exc:
        messages.error(request, f'Google Calendar connection failed: {exc}')
        return redirect('faculty:profile')
    return redirect('faculty:profile')


@login_required
@role_required('faculty')
@csrf_protect
def calendar_disconnect(request):
    """Revoke the faculty member's Google Calendar access and clear local links."""
    if request.method != 'POST':
        return HttpResponse(status=405)
    disconnect_google_calendar(request.user)
    return JsonResponse({'status': 'disconnected'})


@login_required
@role_required('faculty')
def calendar_status(request):
    """Return connection, preference, last-sync, and error information as JSON."""
    connection = GoogleCalendarConnection.objects.filter(user=request.user).first()
    faculty = _faculty_for_request(request)
    return JsonResponse({
        'connected': connection is not None,
        'sync_enabled': bool(faculty and faculty.sync_enabled),
        'last_synced_at': connection.last_synced_at.isoformat() if connection and connection.last_synced_at else None,
        'sync_error': connection.last_sync_error if connection else None,
    })


@login_required
@role_required('faculty')
@csrf_protect
def calendar_preference(request):
    """Enable or disable calendar synchronization for the current faculty member."""
    if request.method != 'POST':
        return HttpResponse(status=405)
    faculty = _faculty_for_request(request)
    if faculty is None:
        return JsonResponse({'error': 'No faculty profile'}, status=400)
    try:
        payload = _json_body(request)
    except ValueError as exc:
        return HttpResponseBadRequest(str(exc))
    enabled = payload.get('sync_enabled')
    if not isinstance(enabled, bool):
        return JsonResponse({'error': 'sync_enabled must be true or false.'}, status=400)
    connection = GoogleCalendarConnection.objects.filter(user=request.user).first()
    if enabled and connection is None:
        return JsonResponse({'error': 'Connect Google Calendar before enabling sync.'}, status=409)
    faculty.sync_enabled = enabled
    faculty.save(update_fields=['sync_enabled'])
    if enabled:
        try:
            sync_google_calendar(request.user)
        except GoogleCalendarError as exc:
            return JsonResponse({
                'sync_enabled': True,
                'error': str(exc),
            }, status=502)
    return JsonResponse({
        'sync_enabled': faculty.sync_enabled,
        'connected': connection is not None,
        'last_synced_at': connection.last_synced_at.isoformat() if connection and connection.last_synced_at else None,
    })


@login_required
@role_required('faculty')
@csrf_protect
def api_schedule_events(request):
    """List, create, and optionally pull-sync the faculty member's schedule events."""
    faculty = _faculty_for_request(request)
    if faculty is None:
        return JsonResponse({'error': 'No faculty profile'}, status=400)
    refresh_faculty_status(faculty)

    if request.method == 'GET':
        sync_error = None
        sync_requested = request.GET.get('sync') == '1'
        sync_performed = False
        connection = GoogleCalendarConnection.objects.filter(user=request.user).first()
        calendar_connected = connection is not None
        sync_enabled = bool(faculty.sync_enabled and connection)
        if sync_requested and sync_enabled:
            try:
                sync_google_calendar(request.user)
                sync_performed = True
            except GoogleCalendarError as exc:
                sync_error = str(exc)
        elif sync_requested and calendar_connected and not faculty.sync_enabled:
            sync_error = 'Two-way sync is disabled in your profile.'
        elif sync_requested and not calendar_connected:
            sync_error = 'Connect Google Calendar before syncing.'

        events = list(ScheduleEvent.objects.filter(faculty=faculty))
        approved_consultations = list(
            ConsultationRequest.objects.filter(
                faculty=faculty,
                status__in=['approved', 'cancellation_requested'],
            ).select_related('user', 'faculty')
        )
        calendar_events = (
            [_event_json(event) for event in events]
            + [_consultation_event_json(consultation) for consultation in approved_consultations]
        )
        calendar_events.sort(key=lambda event: (event['date'] or '', event['start_time'] or ''))
        return JsonResponse({
            'events': calendar_events,
            'faculty_status': faculty.current_status,
            'calendar_connected': calendar_connected,
            'sync_enabled': sync_enabled,
            'sync_performed': sync_performed,
            'sync_error': sync_error,
        })

    if request.method == 'POST':
        try:
            payload = _json_body(request)
            values = _event_values(payload)
        except ValueError as exc:
            return HttpResponseBadRequest(str(exc))

        event = ScheduleEvent(faculty=faculty, **values)
        connection = GoogleCalendarConnection.objects.filter(user=request.user).first()
        sync_requested = payload.get('sync_to_google')
        if sync_requested is not None and not isinstance(sync_requested, bool):
            return HttpResponseBadRequest('sync_to_google must be true or false')
        if sync_requested is True and faculty.sync_enabled and connection is None:
            return JsonResponse(
                {'error': 'Connect Google Calendar before adding this event to it.'},
                status=409,
            )
        can_sync = bool(event.date or (event.day_of_week and event.start_month and event.end_month))
        sync_enabled = (
            bool(connection and faculty.sync_enabled and can_sync)
            if sync_requested is True
            else bool(connection and faculty.sync_enabled and can_sync)
            if sync_requested is None
            else False
        )
        try:
            if sync_enabled:
                google_event = create_google_event(connection, event)
                event.google_event_id = google_event.get('id')
                event.google_calendar_id = connection.calendar_id
                event.managed_by_facsync = True
                event.sync_state = 'synced'
                if not event.google_event_id:
                    raise GoogleCalendarError('Google Calendar did not return an event ID.')
            event.save()
        except GoogleCalendarError as exc:
            return JsonResponse({'error': str(exc)}, status=502)
        refresh_faculty_status(faculty)
        return JsonResponse(_event_json(event), status=201)

    return HttpResponse(status=405)


@login_required
@role_required('faculty')
@csrf_protect
def api_schedule_events_bulk_delete(request):
    """Delete several faculty schedule events and their managed Google events."""
    if request.method != 'POST':
        return HttpResponse(status=405)

    faculty = _faculty_for_request(request)
    if faculty is None:
        return JsonResponse({'error': 'No faculty profile'}, status=400)
    try:
        payload = _json_body(request)
    except ValueError as exc:
        return HttpResponseBadRequest(str(exc))

    event_ids = payload.get('event_ids')
    if not isinstance(event_ids, list) or not event_ids:
        return JsonResponse({'error': 'Select at least one schedule event to delete.'}, status=400)
    try:
        event_ids = list(dict.fromkeys(int(event_id) for event_id in event_ids))
    except (TypeError, ValueError):
        return JsonResponse({'error': 'event_ids must contain valid event IDs.'}, status=400)

    events = list(ScheduleEvent.objects.filter(faculty=faculty, pk__in=event_ids))
    if len(events) != len(event_ids):
        return JsonResponse({'error': 'One or more selected events could not be found.'}, status=404)

    connection = GoogleCalendarConnection.objects.filter(user=request.user).first()
    # Deletion must still remove a linked Google event when two-way sync has
    # been disabled after the event was originally synchronized.
    calendar_available = bool(connection)
    deleted_ids = []
    try:
        for event in events:
            if calendar_available and event.google_event_id:
                delete_google_event(connection, event)
            deleted_ids.append(event.pk)
            event.delete()
    except GoogleCalendarError as exc:
        return JsonResponse({
            'error': str(exc),
            'deleted_ids': deleted_ids,
            'deleted_count': len(deleted_ids),
        }, status=502)

    refresh_faculty_status(faculty)
    return JsonResponse({
        'status': 'deleted',
        'deleted_ids': deleted_ids,
        'deleted_count': len(deleted_ids),
    })


@login_required
@role_required('faculty')
@csrf_protect
def api_schedule_event_detail(request, pk):
    """Read, update, or delete one faculty schedule event and its Google counterpart."""
    faculty = _faculty_for_request(request)
    if faculty is None:
        return JsonResponse({'error': 'No faculty profile'}, status=400)
    event = get_object_or_404(ScheduleEvent, pk=pk, faculty=faculty)

    if request.method == 'GET':
        return JsonResponse(_event_json(event))

    connection = GoogleCalendarConnection.objects.filter(user=request.user).first()
    sync_enabled = bool(connection and faculty.sync_enabled)
    calendar_available = bool(connection)

    if request.method in ('PUT', 'PATCH'):
        try:
            payload = _json_body(request)
            edit_scope = payload.get('edit_scope', 'all')
            if edit_scope not in ('this', 'all'):
                raise ValueError('edit_scope must be this or all')
            occurrence_date = None
            if edit_scope == 'this':
                try:
                    occurrence_date = date.fromisoformat(str(payload.get('occurrence_date') or ''))
                except ValueError as exc:
                    raise ValueError('A valid occurrence date is required for this-event edits.') from exc
                if (event.date is not None or not event.day_of_week
                        or occurrence_date.strftime('%A').lower() != event.day_of_week
                        or occurrence_date.isoformat() in (event.recurrence_excluded_dates or [])
                        or (event.recurrence_start_date and occurrence_date < event.recurrence_start_date)
                        or (event.recurrence_end_date and occurrence_date > event.recurrence_end_date)):
                    raise ValueError('Select an existing occurrence of this series.')
                edited_date = date.fromisoformat(str(
                    payload.get('date') or payload.get('start_date') or occurrence_date
                ))
                new_day = payload.get('day_of_week')
                if new_day and new_day != event.day_of_week:
                    weekdays = list(SCHEDULE_WEEKDAYS)
                    if new_day not in weekdays:
                        raise ValueError('Invalid day of week')
                    edited_date = occurrence_date + timedelta(
                        days=weekdays.index(new_day) - occurrence_date.weekday(),
                    )
                payload = {
                    **payload,
                    'date': edited_date.isoformat(),
                    'day_of_week': '',
                    'start_month': None,
                    'end_month': None,
                    'start_date': None,
                    'end_date': None,
                }
            values = _event_values(payload, existing=event)
            if edit_scope == 'this':
                values.update({
                    'date': edited_date,
                    'day_of_week': '',
                    'start_month': None,
                    'end_month': None,
                    'recurrence_start_date': None,
                    'recurrence_end_date': None,
                })
        except ValueError as exc:
            return HttpResponseBadRequest(str(exc))
        sync_requested = payload.get('sync_to_google')
        if sync_requested is not None and not isinstance(sync_requested, bool):
            return HttpResponseBadRequest('sync_to_google must be true or false')
        if sync_requested is True and connection is None:
            return JsonResponse(
                {'error': 'Connect Google Calendar before adding this event to it.'},
                status=409,
            )
        if edit_scope == 'this' and event.google_event_id and connection is None:
            return JsonResponse(
                {'error': 'Reconnect Google Calendar before editing this event.'},
                status=409,
            )
        if sync_requested is False and event.google_event_id and connection is None:
            return JsonResponse(
                {'error': 'Reconnect Google Calendar before removing this event from it.'},
                status=409,
            )
        if edit_scope == 'this':
            try:
                if calendar_available and event.google_event_id:
                    delete_google_event_instance(
                        connection,
                        event.google_event_id,
                        occurrence_date,
                    )
                excluded_dates = list(event.recurrence_excluded_dates or [])
                occurrence_key = occurrence_date.isoformat()
                if occurrence_key not in excluded_dates:
                    excluded_dates.append(occurrence_key)
                event.recurrence_excluded_dates = excluded_dates
                event.save(update_fields=['recurrence_excluded_dates', 'updated_at'])

                new_event = ScheduleEvent(
                    faculty=faculty,
                    recurring_parent=event,
                    original_occurrence_date=occurrence_date,
                    uploaded_by=event.uploaded_by,
                    is_csv_upload=event.is_csv_upload,
                    offering_id=event.offering_id,
                    subject_code=event.subject_code,
                    section=event.section,
                    units=event.units,
                    lecture=event.lecture,
                    lab=event.lab,
                    managed_by_facsync=False,
                    sync_state='local',
                    **values,
                )
                new_event.save()
                new_sync_enabled = bool(
                    connection and (
                        sync_requested is True
                        or (sync_requested is None and faculty.sync_enabled)
                    )
                )
                if new_sync_enabled:
                    google_event = create_google_event(connection, new_event)
                    new_event.google_event_id = google_event.get('id')
                    new_event.google_calendar_id = connection.calendar_id
                    new_event.managed_by_facsync = True
                    new_event.sync_state = 'synced'
                    if not new_event.google_event_id:
                        raise GoogleCalendarError('Google Calendar did not return an event ID.')
                    new_event.save(update_fields=[
                        'google_event_id', 'google_calendar_id', 'managed_by_facsync',
                        'sync_state', 'updated_at',
                    ])
            except (GoogleCalendarError, ValueError) as exc:
                return JsonResponse({'error': str(exc)}, status=502)
            refresh_faculty_status(faculty)
            return JsonResponse(_event_json(new_event))

        edited_occurrences = list(event.edited_occurrences.filter(faculty=faculty))
        if any(item.google_event_id for item in edited_occurrences) and not connection:
            return JsonResponse({'error': 'Reconnect Google Calendar before editing this series.'}, status=409)
        restored_dates = {item.original_occurrence_date.isoformat()
                          for item in edited_occurrences if item.original_occurrence_date}
        event.recurrence_excluded_dates = [
            value for value in (event.recurrence_excluded_dates or []) if value not in restored_dates
        ]
        _adjust_recurring_edit(event, values)
        for field, value in values.items():
            setattr(event, field, value)

        can_sync = bool(event.date or (event.day_of_week and event.start_month and event.end_month))
        sync_enabled = (
            bool(connection and faculty.sync_enabled and can_sync)
            if sync_requested is True
            else bool(connection and faculty.sync_enabled and can_sync)
            if sync_requested is None
            else False
        )

        try:
            if sync_requested is False and event.google_event_id:
                delete_google_event(connection, event)
                event.google_event_id = None
                event.google_calendar_id = None
                event.managed_by_facsync = False
                event.sync_state = 'local'
                event.sync_error = ''
            elif event.google_event_id and calendar_available:
                # An explicit sync choice replaces the Google event. This
                # prevents the pre-edit event from remaining visible when an
                # update is represented by a newly-created Google event.
                if sync_requested is True:
                    delete_google_event(connection, event)
                    google_event = create_google_event(connection, event)
                    event.google_event_id = google_event.get('id')
                    event.google_calendar_id = connection.calendar_id
                    event.managed_by_facsync = True
                else:
                    try:
                        update_google_event(connection, event)
                    except GoogleCalendarError as exc:
                        if '(404)' not in str(exc):
                            raise
                        google_event = create_google_event(connection, event)
                        event.google_event_id = google_event.get('id')
                        event.google_calendar_id = connection.calendar_id
                        event.managed_by_facsync = True
                event.sync_state = 'synced'
                event.sync_error = ''
                if not event.google_event_id:
                    raise GoogleCalendarError('Google Calendar did not return an event ID.')
            elif sync_enabled:
                google_event = create_google_event(connection, event)
                event.google_event_id = google_event.get('id')
                event.google_calendar_id = connection.calendar_id
                event.managed_by_facsync = True
                event.sync_state = 'synced'
                event.sync_error = ''
                if not event.google_event_id:
                    raise GoogleCalendarError('Google Calendar did not return an event ID.')
            for occurrence in edited_occurrences:
                if occurrence.google_event_id:
                    delete_google_event(connection, occurrence)
            with transaction.atomic():
                event.save()
                ScheduleEvent.objects.filter(pk__in=[item.pk for item in edited_occurrences]).delete()
        except GoogleCalendarError as exc:
            return JsonResponse({'error': str(exc)}, status=502)
        refresh_faculty_status(faculty)
        return JsonResponse(_event_json(event))

    if request.method == 'DELETE':
        try:
            occurrence_date_value = request.GET.get('occurrence_date')
            if event.date is None and occurrence_date_value:
                try:
                    occurrence_date = date.fromisoformat(occurrence_date_value)
                except ValueError as exc:
                    raise ValueError('Invalid occurrence date.') from exc
                if calendar_available and event.google_event_id:
                    delete_google_event_instance(
                        connection,
                        event.google_event_id,
                        occurrence_date,
                    )
                excluded_dates = list(event.recurrence_excluded_dates or [])
                occurrence_key = occurrence_date.isoformat()
                if occurrence_key not in excluded_dates:
                    excluded_dates.append(occurrence_key)
                    event.recurrence_excluded_dates = excluded_dates
                    event.save(update_fields=['recurrence_excluded_dates', 'updated_at'])
                refresh_faculty_status(faculty)
                return JsonResponse({
                    'status': 'occurrence_deleted',
                    'occurrence_date': occurrence_key,
                })
            series_events = [event, *event.edited_occurrences.filter(faculty=faculty)]
            if any(item.google_event_id and (
                connection is None or (item.google_calendar_id
                                       and item.google_calendar_id != connection.calendar_id)
            ) for item in series_events):
                return JsonResponse({
                    'error': 'Reconnect the original Google Calendar before deleting these events.',
                }, status=409)
            for item in series_events:
                if item.google_event_id:
                    delete_google_event(connection, item)
            with transaction.atomic():
                ScheduleEvent.objects.filter(
                    faculty=faculty, pk__in=[item.pk for item in series_events],
                ).delete()
        except ValueError as exc:
            return HttpResponseBadRequest(str(exc))
        except GoogleCalendarError as exc:
            return JsonResponse({'error': str(exc)}, status=502)
        refresh_faculty_status(faculty)
        return JsonResponse({'status': 'deleted'})

    return HttpResponse(status=405)


def _consultation_json(consultation):
    """Serialize consultation timing and calendar synchronization metadata."""
    return {
        'request_id': consultation.request_id,
        'status': consultation.status,
        'date': consultation.date.isoformat(),
        'start_time': consultation.start_time.isoformat() if consultation.start_time else None,
        'end_time': consultation.end_time.isoformat() if consultation.end_time else None,
        'consultation_type': consultation.consultation_type,
        'consultation_type_label': consultation.get_consultation_type_display(),
        'agenda': consultation.agenda,
        'agenda_label': consultation.get_agenda_display(),
        'google_event_id': consultation.google_event_id,
        'calendar_sync_status': consultation.calendar_sync_status,
        'calendar_sync_error': consultation.calendar_sync_error,
        'last_calendar_sync_at': (
            consultation.last_calendar_sync_at.isoformat()
            if consultation.last_calendar_sync_at else None
        ),
    }


def _consultation_values(payload, existing):
    """Validate and normalize consultation date and time changes."""
    values = {}
    if 'date' in payload:
        try:
            values['date'] = date.fromisoformat(str(payload['date']))
        except (TypeError, ValueError) as exc:
            raise ValueError('Invalid consultation date.') from exc
    if 'start_time' in payload:
        try:
            values['start_time'] = time.fromisoformat(str(payload['start_time'])) if payload['start_time'] else None
        except (TypeError, ValueError) as exc:
            raise ValueError('Invalid consultation start time.') from exc
    if 'end_time' in payload:
        try:
            values['end_time'] = time.fromisoformat(str(payload['end_time'])) if payload['end_time'] else None
        except (TypeError, ValueError) as exc:
            raise ValueError('Invalid consultation end time.') from exc
    if 'date' not in values:
        values['date'] = existing.date
    if 'start_time' not in values:
        values['start_time'] = existing.start_time
    if 'end_time' not in values:
        values['end_time'] = existing.end_time
    if values['start_time'] and values['end_time'] and values['end_time'] <= values['start_time']:
        raise ValueError('Consultation must end after it starts.')
    return values


def _notify_consultation_student(consultation, subject, body):
    """Email a consultation status change to the student when an address exists."""
    if not consultation.user.email:
        return
    send_mail(
        subject,
        body,
        getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@facsync.local'),
        [consultation.user.email],
        fail_silently=True,
    )


@login_required
@role_required('faculty')
@csrf_protect
def api_consultation(request, request_id):
    """Approve, decline, reschedule, cancel, or inspect a consultation request."""
    consultation = get_object_or_404(
        ConsultationRequest.objects.select_related('faculty', 'faculty__user', 'user'),
        request_id=request_id,
    )
    is_faculty = request.user == consultation.faculty.user
    is_student = request.user == consultation.user
    if not is_faculty and not is_student:
        return JsonResponse({'error': 'You cannot modify this consultation.'}, status=403)

    connection = GoogleCalendarConnection.objects.filter(
        user=consultation.faculty.user,
    ).first()
    sync_enabled = bool(connection and consultation.faculty.sync_enabled)

    if request.method == 'POST':
        if not is_faculty:
            return JsonResponse({'error': 'Only faculty can approve or decline requests.'}, status=403)
        try:
            payload = _json_body(request)
        except ValueError as exc:
            return HttpResponseBadRequest(str(exc))
        new_status = payload.get('status')
        allowed_statuses = {'approved', 'declined', 'cancelled', 'completed'}
        if new_status not in allowed_statuses:
            return JsonResponse({'error': 'Invalid consultation status.'}, status=400)
        old_status = consultation.status
        allowed_transitions = {
            'pending': {'approved', 'declined', 'cancelled'},
            'approved': {'completed', 'cancelled'},
            'cancellation_requested': {'approved', 'cancelled'},
        }
        if new_status not in allowed_transitions.get(old_status, set()):
            return JsonResponse({'error': 'This request has changed. Refresh before trying again.'}, status=409)
        rejecting_cancellation = old_status == 'cancellation_requested' and new_status == 'approved'
        if new_status == 'approved' and sync_enabled and not rejecting_cancellation:
            try:
                has_calendar_conflict = consultation_has_calendar_conflict(connection, consultation)
            except GoogleCalendarError as exc:
                return JsonResponse({
                    'error': f'Unable to check Google Calendar: {exc}',
                }, status=409)
            if has_calendar_conflict:
                return JsonResponse({
                    'error': 'The faculty calendar has an overlapping event.',
                    'calendar_conflict': True,
                }, status=409)
        consultation.status = new_status
        if new_status == 'approved' and not consultation.approved_at:
            consultation.approved_at = timezone.now()
        if 'faculty_note' in payload:
            consultation.faculty_note = str(payload.get('faculty_note') or '').strip()

        if new_status == 'approved' and not rejecting_cancellation:
            consultation.calendar_sync_status = 'not_configured'
            consultation.calendar_sync_error = ''
            if sync_enabled:
                try:
                    google_event = create_consultation_event(connection, consultation)
                    consultation.google_event_id = google_event.get('id')
                    consultation.google_calendar_id = connection.calendar_id
                    consultation.calendar_sync_status = 'synced'
                    consultation.last_calendar_sync_at = timezone.now()
                    if not consultation.google_event_id:
                        raise GoogleCalendarError('Google Calendar did not return an event ID.')
                except GoogleCalendarError as exc:
                    consultation.calendar_sync_status = 'failed'
                    consultation.calendar_sync_error = str(exc)
        elif new_status in {'declined', 'cancelled', 'completed'} and old_status in {'approved', 'cancellation_requested'}:
            if consultation.google_event_id and (not connection or (
                consultation.google_calendar_id
                and consultation.google_calendar_id != connection.calendar_id
            )):
                return JsonResponse({'error': 'Reconnect the original calendar before cancelling this appointment.'}, status=409)
            if connection and consultation.google_event_id:
                try:
                    delete_consultation_event(connection, consultation)
                except GoogleCalendarError as exc:
                    return JsonResponse({'error': 'Unable to remove the calendar appointment. Please try again.'}, status=502)
            consultation.google_event_id = None
            consultation.google_calendar_id = None
            if consultation.calendar_sync_status != 'failed':
                consultation.calendar_sync_status = 'not_configured'
        consultation.save()
        if new_status in {'approved', 'declined', 'cancelled'}:
            create_notification(
                recipient=consultation.user,
                notification_type='booking_confirmation',
                title='Cancellation request rejected' if rejecting_cancellation else f'Booking {new_status}',
                message=(
                    f'Your consultation request with {consultation.faculty} was '
                    f'{new_status}.'
                    + (' Your cancellation request was rejected; the appointment remains scheduled.' if rejecting_cancellation else '')
                ),
                url='/student/consultation-requests/',
            )
        if new_status in {'declined', 'cancelled'}:
            _notify_consultation_student(
                consultation,
                f'FacSync consultation {new_status}',
                f'Your consultation request {consultation.request_id} with '
                f'{consultation.faculty} was {new_status}.',
            )
        return JsonResponse(_consultation_json(consultation))

    if request.method == 'PATCH':
        if consultation.status != 'approved':
            return JsonResponse({'error': 'Only approved consultations can be rescheduled.'}, status=409)
        try:
            values = _consultation_values(_json_body(request), consultation)
        except ValueError as exc:
            return HttpResponseBadRequest(str(exc))
        for field, value in values.items():
            setattr(consultation, field, value)
        consultation.calendar_sync_status = 'not_configured'
        consultation.calendar_sync_error = ''
        if sync_enabled:
            try:
                if consultation.google_event_id:
                    try:
                        google_event = update_consultation_event(connection, consultation)
                    except GoogleCalendarError as exc:
                        if '(404)' not in str(exc):
                            raise
                        consultation.google_event_id = None
                        google_event = create_consultation_event(connection, consultation)
                        consultation.google_event_id = google_event.get('id')
                else:
                    google_event = create_consultation_event(connection, consultation)
                    consultation.google_event_id = google_event.get('id')
                consultation.google_calendar_id = connection.calendar_id
                consultation.calendar_sync_status = 'synced'
                consultation.last_calendar_sync_at = timezone.now()
            except GoogleCalendarError as exc:
                consultation.calendar_sync_status = 'failed'
                consultation.calendar_sync_error = str(exc)
        consultation.save()
        return JsonResponse(_consultation_json(consultation))

    if request.method == 'DELETE':
        if consultation.status == 'completed':
            if not is_faculty:
                return JsonResponse({'error': 'Only the faculty member can delete completed consultations.'}, status=403)
            consultation.delete()
            return JsonResponse({'status': 'deleted', 'request_id': request_id})

        if consultation.status == 'approved' and connection and consultation.google_event_id:
            try:
                delete_consultation_event(connection, consultation)
            except GoogleCalendarError as exc:
                consultation.calendar_sync_status = 'failed'
                consultation.calendar_sync_error = str(exc)
        consultation.status = 'cancelled'
        consultation.google_event_id = None
        consultation.google_calendar_id = None
        consultation.save(update_fields=[
            'status', 'google_event_id', 'google_calendar_id',
            'calendar_sync_status', 'calendar_sync_error',
        ])
        _notify_consultation_student(
            consultation,
            'FacSync consultation cancelled',
            f'Your consultation request {consultation.request_id} with '
            f'{consultation.faculty} was cancelled.',
        )
        return JsonResponse(_consultation_json(consultation))

    if request.method == 'GET':
        return JsonResponse(_consultation_json(consultation))
    return HttpResponse(status=405)


@login_required
@role_required('faculty')
@require_GET
@never_cache
def consultation_browser_api(request):
    metric = request.GET.get('metric', '')
    if metric not in FACULTY_BROWSER_QUESTIONS:
        return JsonResponse({'error': 'Unknown consultation question.'}, status=400)
    faculty = FacultyProfile.objects.filter(user=request.user).first()
    if not faculty or not str(faculty.college_id or '').strip():
        return JsonResponse({'error': 'Your faculty profile has no college set.'}, status=400)
    return JsonResponse(consultation_browser_answer(metric, faculty))
