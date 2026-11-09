"""Read-only overlap warnings for manual schedule edits, before any writes."""
import hashlib
import json
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.conf import settings
from django.core import signing
from django.utils import timezone

from apps.faculty.models import ConsultationRequest, ScheduleEvent
from .google_calendar import _parse_google_datetime, list_google_events
from .schedule_conflicts import occurrence_interval, overlaps, schedule_intervals

SALT = 'faculty-manual-event-overlap-v1'


def candidate_intervals(event):
    if event.date:
        return [occurrence_interval(event.date, event.start_time, event.end_time)]
    if not event.day_of_week or not event.start_month or not event.end_month:
        return []  # Undated time-only entries do not have calendar occurrences.
    today = timezone.localdate()
    start = event.recurrence_start_date or date(today.year, event.start_month, 1)
    if event.recurrence_end_date:
        end = event.recurrence_end_date
    else:
        import calendar
        year = start.year + (event.end_month < event.start_month)
        end = date(year, event.end_month, calendar.monthrange(year, event.end_month)[1])
        if not event.recurrence_start_date and end < today:
            start = start.replace(year=start.year + 1)
            end = end.replace(year=end.year + 1)
    weekday = [key for key, _ in ScheduleEvent.WEEKDAY_CHOICES].index(event.day_of_week)
    current = start + timedelta(days=(weekday - start.weekday()) % 7)
    result = []
    while current <= end:
        if current.isoformat() not in (event.recurrence_excluded_dates or []):
            result.append(occurrence_interval(current, event.start_time, event.end_time))
        if len(result) > 2000:
            raise ValueError('Choose a shorter recurring date range to check calendar overlaps.')
        current += timedelta(days=7)
    return result


def manual_event_overlaps(faculty, candidate, connection=None, *, existing=None, edit_scope='all', occurrence_date=None):
    intervals = candidate_intervals(candidate)
    if not intervals:
        return []
    zone = ZoneInfo(getattr(settings, 'GOOGLE_CALENDAR_TIME_ZONE', settings.TIME_ZONE))
    found = {}
    replaced = {existing.pk} if existing and edit_scope == 'all' else set()
    if replaced:
        replaced.update(existing.edited_occurrences.values_list('pk', flat=True))
    local = list(ScheduleEvent.objects.filter(faculty=faculty))
    local_google_ids = {item.google_event_id for item in local if item.google_event_id}
    excluded_google = {item.google_event_id for item in local if item.pk in replaced and item.google_event_id}

    def record(key, title, source, start, end):
        found.setdefault((str(key), start, end), {
            'title': title, 'source': source,
            'start': start.replace(tzinfo=zone).isoformat(), 'end': end.replace(tzinfo=zone).isoformat(),
        })

    for item in local:
        if item.pk in replaced:
            continue
        for start, end in intervals:
            for day in {start.date(), end.date()}:
                for other_start, other_end in schedule_intervals(item, day):
                    if existing and edit_scope == 'this' and item.pk == existing.pk:
                        original = occurrence_interval(occurrence_date, existing.start_time, existing.end_time)
                        if (other_start, other_end) == original:
                            continue
                    if overlaps(start, end, other_start, other_end):
                        record(item.google_event_id or f'local:{item.pk}', item.title, 'FacSync', other_start, other_end)

    for item in ConsultationRequest.objects.filter(faculty=faculty,
            status__in=['approved', 'cancellation_requested'], date__gte=intervals[0][0].date() - timedelta(days=1),
            date__lte=intervals[-1][1].date()).select_related('user'):
        other_start, other_end = occurrence_interval(item.date, item.start_time, item.end_time)
        if any(overlaps(start, end, other_start, other_end) for start, end in intervals):
            record(item.google_event_id or f'consultation:{item.pk}',
                f'Consultation with {item.user.get_full_name() or item.user.username}', 'FacSync', other_start, other_end)

    if connection:
        for item in list_google_events(connection,
                time_min=intervals[0][0].replace(tzinfo=zone).isoformat(),
                time_max=intervals[-1][1].replace(tzinfo=zone).isoformat()):
            if (item.get('status') == 'cancelled' or item.get('transparency') == 'transparent'
                    or any(person.get('self') and person.get('responseStatus') == 'declined' for person in item.get('attendees', []))
                    or item.get('id') in excluded_google or item.get('recurringEventId') in excluded_google):
                continue
            begin, finish = item.get('start') or {}, item.get('end') or {}
            if begin.get('dateTime') and finish.get('dateTime'):
                other_start = _parse_google_datetime(begin['dateTime']).replace(tzinfo=None)
                other_end = _parse_google_datetime(finish['dateTime']).replace(tzinfo=None)
            elif begin.get('date'):
                other_start = datetime.combine(date.fromisoformat(begin['date']), time.min)
                other_end = datetime.combine(date.fromisoformat(finish.get('date') or begin['date']), time.min)
                if other_end <= other_start:
                    other_end = other_start + timedelta(days=1)
            else:
                continue
            original = item.get('originalStartTime') or begin
            original_day = (original.get('date') or
                (_parse_google_datetime(original['dateTime']).date().isoformat() if original.get('dateTime') else ''))
            if (existing and edit_scope == 'this' and occurrence_date
                    and (item.get('recurringEventId') == existing.google_event_id or item.get('id') == existing.google_event_id)
                    and original_day == occurrence_date.isoformat()):
                continue
            if any(overlaps(start, end, other_start, other_end) for start, end in intervals):
                identity = item.get('id') if item.get('id') in local_google_ids else (item.get('recurringEventId') or item.get('id'))
                record(identity, item.get('summary') or 'Untitled Google event', 'Google Calendar', other_start, other_end)
    return sorted(found.values(), key=lambda item: (item['start'], item['title']))


def overlap_warning(faculty, candidate, payload, conflicts, *, existing=None):
    """Only a fresh, server-signed acknowledgement of this exact warning bypasses it."""
    if not conflicts:
        return None
    data = {key: value for key, value in payload.items() if key != 'overlap_confirmation'}
    fingerprint = hashlib.sha256(json.dumps({'faculty':faculty.pk, 'event':existing.pk if existing else None,
        'updated_at':str(existing.updated_at) if existing else None, 'payload':data, 'conflicts':conflicts},
        sort_keys=True, default=str).encode()).hexdigest()
    token = payload.get('overlap_confirmation')
    if isinstance(token, str):
        try:
            if signing.loads(token, salt=SALT, max_age=600) == fingerprint:
                return None
        except signing.BadSignature:
            pass
    return {'error':'This event overlaps an existing calendar commitment. Review before saving.',
        'code':'schedule_overlap', 'conflicts':conflicts[:20], 'conflict_count':len(conflicts),
        'overlap_confirmation':signing.dumps(fingerprint, salt=SALT)}
