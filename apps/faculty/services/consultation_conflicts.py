"""Shared appointment and schedule occupancy for new bookings and decisions.

Callers serialize booking changes by locking the faculty owner's User row.
Pending requests do not reserve time. Endpoints touching a boundary may meet.
"""
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.conf import settings

from apps.faculty.models import ConsultationRequest, GoogleCalendarConnection
from .schedule_conflicts import eligible_schedule_events, occurrence_interval, overlaps, schedule_intervals
from .google_calendar import GoogleCalendarError, _parse_google_datetime, list_google_events

OCCUPIED_STATUSES = ('approved', 'cancellation_requested')
OCCUPIED_MESSAGE = 'The faculty member is unavailable during this time. Please choose another time.'
VERIFICATION_MESSAGE = 'Unable to verify availability. Please try again.'


def consultation_interval(day, start_time, end_time):
    if start_time is not None and end_time is None:
        start = datetime.combine(day, start_time)
        return start, start + timedelta(hours=1)
    return occurrence_interval(day, start_time, end_time)


def has_appointment_conflict(faculty, day, start_time, end_time, *, exclude_request_id=None):
    start, end = consultation_interval(day, start_time, end_time)
    appointments = ConsultationRequest.objects.filter(
        faculty=faculty, status__in=OCCUPIED_STATUSES,
        date__gte=day - timedelta(days=1), date__lte=end.date(),
    )
    if exclude_request_id is not None:
        appointments = appointments.exclude(pk=exclude_request_id)
    return any(overlaps(start, end, *consultation_interval(row.date, row.start_time, row.end_time))
               for row in appointments.only('date', 'start_time', 'end_time'))


def _blocks(event_type, consultation_type):
    return event_type != 'virtual' or consultation_type != 'online'


def _google_interval(item):
    begin, finish = item.get('start') or {}, item.get('end') or {}
    try:
        if begin.get('dateTime') and finish.get('dateTime'):
            start = _parse_google_datetime(begin['dateTime']).replace(tzinfo=None)
            end = _parse_google_datetime(finish['dateTime']).replace(tzinfo=None)
        elif begin.get('date') and finish.get('date'):
            start = datetime.combine(date.fromisoformat(begin['date']), time.min)
            end = datetime.combine(date.fromisoformat(finish['date']), time.min)
        else:
            raise ValueError('Missing calendar interval')
        if end <= start:
            raise ValueError('Invalid calendar interval')
        return start, end
    except (ValueError, TypeError, KeyError) as error:
        raise GoogleCalendarError('Unable to read calendar availability.') from error


def booking_conflict(faculty, day, start_time, end_time, consultation_type, *, exclude_request_id=None,
                     google_events=None):
    if has_appointment_conflict(faculty, day, start_time, end_time, exclude_request_id=exclude_request_id):
        return 'appointment'
    start, end = consultation_interval(day, start_time, end_time)
    connection = GoogleCalendarConnection.objects.filter(user_id=faculty.user_id).first()
    events = list(eligible_schedule_events().filter(faculty=faculty))
    linked = {row.google_event_id: row for row in events if connection and row.google_event_id
              and row.google_calendar_id == connection.calendar_id}
    local_ids = {str(row.pk): row for row in events}
    for event in events:
        # Current Google instances supersede a synced mirror, including deleted,
        # moved, transparent, and modified recurring occurrences.
        if (connection and event.google_calendar_id == connection.calendar_id
                and event.google_event_id in linked and event.sync_state == 'synced'):
            continue
        if not _blocks(event.event_type, consultation_type):
            continue
        current = start.date()
        while current <= end.date():
            if any(overlaps(start, end, a, b) for a, b in schedule_intervals(event, current)):
                return 'schedule'
            current += timedelta(days=1)
    if connection is None:
        return None
    zone = ZoneInfo(getattr(settings, 'GOOGLE_CALENDAR_TIME_ZONE', settings.TIME_ZONE))
    excluded_google_id = None
    if exclude_request_id:
        excluded_google_id = ConsultationRequest.objects.filter(pk=exclude_request_id, faculty=faculty,
            google_calendar_id=connection.calendar_id).values_list('google_event_id', flat=True).first()
    items = google_events if google_events is not None else list_google_events(connection,
        time_min=start.replace(tzinfo=zone).isoformat(), time_max=end.replace(tzinfo=zone).isoformat())
    for item in items:
        if (item.get('status') == 'cancelled' or item.get('transparency') == 'transparent'
                or any(person.get('self') and person.get('responseStatus') == 'declined'
                       for person in item.get('attendees', []))):
            continue
        private = (item.get('extendedProperties') or {}).get('private') or {}
        if exclude_request_id and ((excluded_google_id and item.get('id') == excluded_google_id)
                or (private.get('facsync_type') == 'consultation' and private.get('facsync_id') == str(exclude_request_id))):
            continue
        event = linked.get(item.get('id')) or linked.get(item.get('recurringEventId'))
        if event is None and private.get('facsync_type') == 'schedule':
            event = local_ids.get(str(private.get('facsync_id')))
        kind = 'on-leave' if item.get('eventType') == 'outOfOffice' else event.event_type if event else 'busy'
        if _blocks(kind, consultation_type) and overlaps(start, end, *_google_interval(item)):
            return 'calendar'
    return None


def booking_conflict_payload(*args, **kwargs):
    """Return a privacy-safe rejection, or None when availability is verified."""
    try:
        reason = booking_conflict(*args, **kwargs)
    except GoogleCalendarError:
        return {'error': VERIFICATION_MESSAGE, 'availability_check_failed': True}
    if reason:
        return {'error': OCCUPIED_MESSAGE, reason + '_conflict': True}
    return None
