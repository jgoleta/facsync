import secrets
from datetime import date, datetime, time, timedelta
from hmac import compare_digest
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

import requests
from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone
from core.services import notify_faculty_status_subscribers

from faculty.models import (
    ConsultationRequest,
    FacultyProfile,
    GoogleCalendarConnection,
    ScheduleEvent,
    StatusHistory,
)


GOOGLE_AUTH_URL = 'https://accounts.google.com/o/oauth2/v2/auth'
GOOGLE_TOKEN_URL = 'https://oauth2.googleapis.com/token'
GOOGLE_USERINFO_URL = 'https://www.googleapis.com/oauth2/v3/userinfo'
GOOGLE_CALENDAR_URL = 'https://www.googleapis.com/calendar/v3'
GOOGLE_CALENDAR_SCOPE = getattr(
    settings,
    'GOOGLE_CALENDAR_SCOPE',
    'https://www.googleapis.com/auth/calendar.events',
)


class GoogleCalendarError(Exception):
    pass


def _client_credentials():
    """Return configured Google OAuth client credentials or raise a clear error."""
    client_id = getattr(settings, 'GOOGLE_CLIENT_ID', '')
    client_secret = getattr(settings, 'GOOGLE_CLIENT_SECRET', '')
    if not client_id or not client_secret:
        raise GoogleCalendarError('Google Calendar credentials are not configured.')
    return client_id, client_secret


def callback_url(request):
    """Return the configured OAuth callback URL for the current deployment."""
    configured_url = getattr(settings, 'GOOGLE_CALENDAR_REDIRECT_URI', '')
    if configured_url:
        return configured_url
    return request.build_absolute_uri(reverse('faculty:calendar_connect'))


def start_oauth(request):
    """Build the Google consent URL and store a CSRF-resistant OAuth state value."""
    client_id, _ = _client_credentials()
    state = secrets.token_urlsafe(32)
    request.session['google_calendar_oauth_state'] = state
    params = {
        'client_id': client_id,
        'redirect_uri': callback_url(request),
        'response_type': 'code',
        'scope': GOOGLE_CALENDAR_SCOPE,
        'access_type': 'offline',
        'prompt': 'select_account consent',
        'login_hint': request.user.email,
        'include_granted_scopes': 'true',
        'state': state,
    }
    return f'{GOOGLE_AUTH_URL}?{urlencode(params)}'


def _token_request(data):
    """Send a token request to Google and convert failures to a service error."""
    try:
        response = requests.post(GOOGLE_TOKEN_URL, data=data, timeout=20)
    except requests.RequestException as exc:
        raise GoogleCalendarError('Unable to contact Google OAuth.') from exc
    if not response.ok:
        try:
            details = response.json()
        except ValueError:
            details = {}
        reason = details.get('error_description') or details.get('error')
        suffix = f': {reason}' if reason else ''
        raise GoogleCalendarError(f'Google OAuth token exchange failed{suffix}.')
    return response.json()


def finish_oauth(request, code, state):
    """Exchange an authorization code, validate the account, and save its tokens."""
    expected_state = request.session.pop('google_calendar_oauth_state', None)
    if not expected_state or not state or not compare_digest(expected_state, state):
        raise GoogleCalendarError('Invalid Google OAuth state.')

    client_id, client_secret = _client_credentials()
    token_data = _token_request({
        'code': code,
        'client_id': client_id,
        'client_secret': client_secret,
        'redirect_uri': callback_url(request),
        'grant_type': 'authorization_code',
    })
    access_token = token_data.get('access_token')
    if not access_token:
        raise GoogleCalendarError('Google did not return an access token.')

    try:
        userinfo_response = requests.get(
            GOOGLE_USERINFO_URL,
            headers={'Authorization': f'Bearer {access_token}'},
            timeout=20,
        )
    except requests.RequestException as exc:
        raise GoogleCalendarError('Unable to verify the Google account.') from exc
    if not userinfo_response.ok:
        raise GoogleCalendarError('Unable to verify the Google account.')

    userinfo = userinfo_response.json()
    google_email = (userinfo.get('email') or '').casefold()
    local_email = (request.user.email or '').casefold()
    if not google_email or google_email != local_email:
        raise GoogleCalendarError('Connect the same Google account used for FacSync.')

    existing = GoogleCalendarConnection.objects.filter(user=request.user).first()
    refresh_token = token_data.get('refresh_token') or (existing.refresh_token if existing else '')
    expires_in = int(token_data.get('expires_in', 3600))
    connection, _ = GoogleCalendarConnection.objects.update_or_create(
        user=request.user,
        defaults={
            'google_user_id': userinfo.get('sub', ''),
            'calendar_id': existing.calendar_id if existing else 'primary',
            'access_token': access_token,
            'refresh_token': refresh_token,
            'token_expires_at': timezone.now() + timedelta(seconds=expires_in),
        },
    )
    return connection


def _refresh_access_token(connection):
    """Refresh an expired access token and persist the replacement token."""
    if not connection.refresh_token:
        raise GoogleCalendarError('Google authorization has expired. Reconnect Google Calendar.')
    client_id, client_secret = _client_credentials()
    token_data = _token_request({
        'client_id': client_id,
        'client_secret': client_secret,
        'refresh_token': connection.refresh_token,
        'grant_type': 'refresh_token',
    })
    if not token_data.get('access_token'):
        raise GoogleCalendarError('Google authorization has expired. Reconnect Google Calendar.')
    connection.access_token = token_data['access_token']
    connection.token_expires_at = timezone.now() + timedelta(
        seconds=int(token_data.get('expires_in', 3600))
    )
    connection.save(update_fields=['access_token', 'token_expires_at', 'updated_at'])
    return connection.access_token


def _access_token(connection, force_refresh=False):
    """Return a usable access token, refreshing it when it is near expiry."""
    if not force_refresh and connection.token_expires_at:
        if connection.token_expires_at > timezone.now() + timedelta(seconds=60):
            return connection.access_token
    if not force_refresh and connection.access_token and not connection.refresh_token:
        return connection.access_token
    return _refresh_access_token(connection)


def google_request(connection, method, path, **kwargs):
    """Make an authenticated Calendar API request with refresh and retry handling."""
    url = f'{GOOGLE_CALENDAR_URL}{path}'
    force_refresh = False
    for attempt in range(3):
        headers = kwargs.pop('headers', {}).copy()
        headers['Authorization'] = f'Bearer {_access_token(connection, force_refresh=force_refresh)}'
        try:
            response = requests.request(method, url, headers=headers, timeout=20, **kwargs)
        except requests.RequestException as exc:
            if attempt == 2:
                raise GoogleCalendarError('Unable to contact Google Calendar.') from exc
            continue
        if response.status_code == 401 and attempt == 0:
            force_refresh = True
            continue
        if response.status_code in (429, 500, 502, 503, 504) and attempt < 2:
            continue
        if not response.ok:
            try:
                details = response.json()
            except ValueError:
                details = {}
            reason = (details.get('error') or {}).get('message') if isinstance(details.get('error'), dict) else details.get('error_description')
            suffix = f': {reason}' if reason else ''
            raise GoogleCalendarError(
                f'Google Calendar request failed ({response.status_code}){suffix}.'
            )
        return response
    raise GoogleCalendarError('Google Calendar authorization failed.')


def list_google_events(connection):
    """Fetch calendar events in the configured past/future synchronization window."""
    events = []
    page_token = None
    while True:
        params = {
            'singleEvents': 'true',
            'showDeleted': 'false',
            'maxResults': 2500,
            'orderBy': 'startTime',
            'timeZone': getattr(settings, 'GOOGLE_CALENDAR_TIME_ZONE', settings.TIME_ZONE),
            'timeMin': (
                timezone.now() - timedelta(
                    days=getattr(settings, 'GOOGLE_CALENDAR_SYNC_PAST_DAYS', 1)
                )
            ).isoformat(),
            'timeMax': (
                timezone.now() + timedelta(
                    days=getattr(settings, 'GOOGLE_CALENDAR_SYNC_FUTURE_DAYS', 60)
                )
            ).isoformat(),
        }
        if page_token:
            params['pageToken'] = page_token
        response = google_request(
            connection,
            'GET',
            f'/calendars/{connection.calendar_id}/events',
            params=params,
        )
        payload = response.json()
        events.extend(payload.get('items', []))
        page_token = payload.get('nextPageToken')
        if not page_token:
            return events


def _parse_google_datetime(value):
    """Parse a Google timestamp and convert it to the configured calendar timezone."""
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
    calendar_timezone = ZoneInfo(
        getattr(settings, 'GOOGLE_CALENDAR_TIME_ZONE', settings.TIME_ZONE)
    )
    return timezone.localtime(parsed, calendar_timezone)


def _google_event_values(item, existing=None):
    """Map a Google event response into fields used by a local schedule event."""
    start = item.get('start') or {}
    end = item.get('end') or {}
    if start.get('date'):
        event_date = date.fromisoformat(start['date'])
        start_time = None
        end_time = None
    elif start.get('dateTime'):
        start_dt = _parse_google_datetime(start['dateTime'])
        end_dt = _parse_google_datetime(end['dateTime']) if end.get('dateTime') else None
        event_date = start_dt.date()
        start_time = start_dt.time().replace(tzinfo=None)
        end_time = end_dt.time().replace(tzinfo=None) if end_dt else None
    else:
        return None

    event_type = (existing.event_type if existing else None) or 'busy'
    if item.get('eventType') == 'outOfOffice':
        event_type = 'on-leave'
    return {
        'title': (item.get('summary') or 'Untitled event')[:128],
        'description': item.get('description') or '',
        'event_type': event_type,
        'date': event_date,
        'start_time': start_time,
        'end_time': end_time,
    }


def google_event_payload(event):
    """Build the Google Calendar request body for a local schedule event."""
    payload = {
        'summary': event.title,
        'description': event.description or '',
    }
    if event.pk:
        payload['extendedProperties'] = {
            'private': {
                'facsync_type': 'schedule',
                'facsync_id': str(event.pk),
            }
        }
    tz_name = getattr(settings, 'GOOGLE_CALENDAR_TIME_ZONE', settings.TIME_ZONE)
    if event.event_type == 'on-leave' or not event.start_time:
        payload['start'] = {'date': event.date.isoformat()}
        payload['end'] = {'date': (event.date + timedelta(days=1)).isoformat()}
        return payload

    start = datetime.combine(event.date, event.start_time)
    end_time = event.end_time or (event.start_time + timedelta(hours=1))
    end = datetime.combine(event.date, end_time)
    if end <= start:
        end += timedelta(days=1)
    current_timezone = ZoneInfo(tz_name)
    payload['start'] = {
        'dateTime': timezone.make_aware(start, current_timezone).isoformat(),
        'timeZone': tz_name,
    }
    payload['end'] = {
        'dateTime': timezone.make_aware(end, current_timezone).isoformat(),
        'timeZone': tz_name,
    }
    return payload


def create_google_event(connection, event):
    """Create a local schedule event in the faculty member's Google Calendar."""
    response = google_request(
        connection,
        'POST',
        f'/calendars/{connection.calendar_id}/events',
        json=google_event_payload(event),
    )
    return response.json()


def consultation_event_payload(consultation):
    """Build a Calendar event body, including the student attendee and FacSync ID."""
    student_name = consultation.user.get_full_name() or consultation.user.email or 'Student'
    payload = {
        'summary': f'FacSync consultation with {student_name}',
        'description': (
            f'Request ID: {consultation.request_id}\n'
            f'{consultation.faculty_note or "Consultation scheduled through FacSync."}'
        ),
    }
    if consultation.user.email:
        payload['attendees'] = [{'email': consultation.user.email}]
    if consultation.start_time:
        tz_name = getattr(settings, 'GOOGLE_CALENDAR_TIME_ZONE', settings.TIME_ZONE)
        start = datetime.combine(consultation.date, consultation.start_time)
        end_time = consultation.end_time or (consultation.start_time + timedelta(hours=1))
        end = datetime.combine(consultation.date, end_time)
        if end <= start:
            end += timedelta(days=1)
        current_timezone = ZoneInfo(tz_name)
        payload['start'] = {
            'dateTime': timezone.make_aware(start, current_timezone).isoformat(),
            'timeZone': tz_name,
        }
        payload['end'] = {
            'dateTime': timezone.make_aware(end, current_timezone).isoformat(),
            'timeZone': tz_name,
        }
    else:
        payload['start'] = {'date': consultation.date.isoformat()}
        payload['end'] = {'date': (consultation.date + timedelta(days=1)).isoformat()}
    payload['extendedProperties'] = {
        'private': {
            'facsync_type': 'consultation',
            'facsync_id': str(consultation.request_id),
        }
    }
    return payload


def create_consultation_event(connection, consultation):
    """Create a Google Calendar event for an approved consultation."""
    response = google_request(
        connection,
        'POST',
        f'/calendars/{connection.calendar_id}/events',
        params={'sendUpdates': 'all'},
        json=consultation_event_payload(consultation),
    )
    return response.json()


def update_consultation_event(connection, consultation):
    """Update the existing Google Calendar event for a consultation."""
    response = google_request(
        connection,
        'PUT',
        f'/calendars/{connection.calendar_id}/events/{consultation.google_event_id}',
        params={'sendUpdates': 'all'},
        json=consultation_event_payload(consultation),
    )
    return response.json()


def delete_consultation_event(connection, consultation):
    """Delete a consultation event, treating an already-deleted event as complete."""
    if not consultation.google_event_id:
        return
    try:
        google_request(
            connection,
            'DELETE',
            f'/calendars/{connection.calendar_id}/events/{consultation.google_event_id}',
            params={'sendUpdates': 'all'},
        )
    except GoogleCalendarError as exc:
        if '(404)' not in str(exc):
            raise


def calendar_sync_enabled(user):
    """Return whether a faculty member has both an active connection and sync enabled."""
    faculty = FacultyProfile.objects.filter(user=user).first()
    return bool(
        faculty and faculty.sync_enabled and
        GoogleCalendarConnection.objects.filter(user=user).exists()
    )


def consultation_has_calendar_conflict(connection, consultation):
    """Return true when a non-transparent Google event overlaps the request."""
    if not consultation.start_time:
        return False
    start = datetime.combine(consultation.date, consultation.start_time)
    end = datetime.combine(
        consultation.date,
        consultation.end_time or (consultation.start_time + timedelta(hours=1)),
    )
    if end <= start:
        end += timedelta(days=1)
    tz_name = getattr(settings, 'GOOGLE_CALENDAR_TIME_ZONE', settings.TIME_ZONE)
    local_tz = ZoneInfo(tz_name)
    requested_start = timezone.make_aware(start, local_tz)
    requested_end = timezone.make_aware(end, local_tz)
    for item in list_google_events(connection):
        if item.get('status') == 'cancelled' or item.get('transparency') == 'transparent':
            continue
        if (
            item.get('extendedProperties', {}).get('private', {}).get('facsync_id')
            == str(consultation.request_id)
        ):
            continue
        values = _google_event_values(item)
        if not values or not values['start_time']:
            if values and values['date'] == consultation.date:
                return True
            continue
        event_start = timezone.make_aware(
            datetime.combine(values['date'], values['start_time']), local_tz
        )
        event_end = timezone.make_aware(
            datetime.combine(values['date'], values['end_time'] or values['start_time']),
            local_tz,
        )
        if event_end <= event_start:
            event_end += timedelta(days=1)
        if event_start < requested_end and requested_start < event_end:
            return True
    return False


def update_google_event(connection, event):
    """Update an existing local schedule event in Google Calendar."""
    response = google_request(
        connection,
        'PUT',
        f'/calendars/{connection.calendar_id}/events/{event.google_event_id}',
        json=google_event_payload(event),
    )
    return response.json()


def delete_google_event(connection, event):
    """Delete a local schedule event from Google Calendar when it still exists."""
    if not event.google_event_id:
        return
    try:
        google_request(
            connection,
            'DELETE',
            f'/calendars/{connection.calendar_id}/events/{event.google_event_id}',
        )
    except GoogleCalendarError as exc:
        # A record already deleted in Google is already in the desired state.
        if '(404)' not in str(exc):
            raise


def sync_google_calendar(user):
    """Pull calendar data, reconcile local records, update status, and record sync time."""
    connection = GoogleCalendarConnection.objects.get(user=user)
    faculty = FacultyProfile.objects.get(user=user)
    try:
        google_events = list_google_events(connection)
        seen_ids = set()
        imported_event_ids = set()
        consultation_event_ids = set()

        for item in google_events:
            if item.get('status') == 'cancelled' or not item.get('id'):
                continue
            event_id = item['id']
            private = (item.get('extendedProperties') or {}).get('private') or {}
            event_kind = private.get('facsync_type')
            event = ScheduleEvent.objects.filter(
                faculty=faculty,
                google_calendar_id=connection.calendar_id,
                google_event_id=event_id,
            ).first()
            values = _google_event_values(item, existing=event)
            if values is None:
                continue

            if event_kind == 'consultation':
                consultation_id = private.get('facsync_id')
                consultation = ConsultationRequest.objects.filter(
                    request_id=consultation_id,
                    faculty=faculty,
                ).first()
                if consultation:
                    consultation_event_ids.add(event_id)
                    # Manual edits to a FacSync event are intentionally
                    # reconciled back into the consultation record on poll.
                    consultation.date = values['date']
                    consultation.start_time = values['start_time']
                    consultation.end_time = values['end_time']
                    consultation.google_event_id = event_id
                    consultation.google_calendar_id = connection.calendar_id
                    consultation.calendar_sync_status = 'synced'
                    consultation.calendar_sync_error = ''
                    consultation.last_calendar_sync_at = timezone.now()
                    consultation.save(update_fields=[
                        'date', 'start_time', 'end_time', 'google_event_id',
                        'google_calendar_id', 'calendar_sync_status',
                        'calendar_sync_error', 'last_calendar_sync_at',
                    ])
                continue

            seen_ids.add(event_id)
            if event:
                values['google_event_id'] = event_id
                values['google_calendar_id'] = connection.calendar_id
                values['sync_state'] = 'synced'
                values['sync_error'] = ''
                for field, value in values.items():
                    setattr(event, field, value)
                event.save(update_fields=list(values.keys()) + ['updated_at'])
            else:
                ScheduleEvent.objects.create(
                    faculty=faculty,
                    google_event_id=event_id,
                    google_calendar_id=connection.calendar_id,
                    sync_state='synced',
                    **values,
                )
            imported_event_ids.add(event_id)

        # Only reconcile records in the configured time window. Events outside
        # it were not fetched and must not be treated as deleted.
        window_start = timezone.localtime(
            timezone.now() - timedelta(days=getattr(settings, 'GOOGLE_CALENDAR_SYNC_PAST_DAYS', 1)),
            ZoneInfo(getattr(settings, 'GOOGLE_CALENDAR_TIME_ZONE', settings.TIME_ZONE)),
        ).date()
        window_end = timezone.localtime(
            timezone.now() + timedelta(days=getattr(settings, 'GOOGLE_CALENDAR_SYNC_FUTURE_DAYS', 60)),
            ZoneInfo(getattr(settings, 'GOOGLE_CALENDAR_TIME_ZONE', settings.TIME_ZONE)),
        ).date()
        tracked_events = ScheduleEvent.objects.filter(
            faculty=faculty,
            google_calendar_id=connection.calendar_id,
            google_event_id__isnull=False,
            date__gte=window_start,
            date__lte=window_end,
        )
        for event in tracked_events:
            if event.google_event_id in imported_event_ids:
                continue
            if event.managed_by_facsync and faculty.sync_enabled:
                try:
                    replacement = create_google_event(connection, event)
                    event.google_event_id = replacement.get('id')
                    event.sync_state = 'synced'
                    event.sync_error = ''
                    event.save(update_fields=['google_event_id', 'sync_state', 'sync_error', 'updated_at'])
                except GoogleCalendarError as exc:
                    event.sync_state = 'out_of_sync'
                    event.sync_error = str(exc)
                    event.save(update_fields=['sync_state', 'sync_error', 'updated_at'])
            else:
                event.sync_state = 'out_of_sync'
                event.sync_error = 'Event no longer exists in Google Calendar.'
                event.save(update_fields=['sync_state', 'sync_error', 'updated_at'])

        consultations = ConsultationRequest.objects.filter(
            faculty=faculty,
            google_calendar_id=connection.calendar_id,
            google_event_id__isnull=False,
            date__gte=window_start,
            date__lte=window_end,
            status='approved',
        )
        for consultation in consultations:
            if consultation.google_event_id in consultation_event_ids:
                continue
            if faculty.sync_enabled:
                try:
                    replacement = create_consultation_event(connection, consultation)
                    consultation.google_event_id = replacement.get('id')
                    consultation.calendar_sync_status = 'synced'
                    consultation.calendar_sync_error = ''
                except GoogleCalendarError as exc:
                    consultation.calendar_sync_status = 'out_of_sync'
                    consultation.calendar_sync_error = str(exc)
                consultation.last_calendar_sync_at = timezone.now()
                consultation.save(update_fields=[
                    'google_event_id', 'calendar_sync_status', 'calendar_sync_error',
                    'last_calendar_sync_at',
                ])

        _update_status_from_calendar(faculty, google_events)
        now = timezone.now()
        connection.last_synced_at = now
        connection.last_sync_error = ''
        connection.save(update_fields=['last_synced_at', 'last_sync_error', 'updated_at'])
        faculty.last_calendar_sync_at = now
        faculty.save(update_fields=['last_calendar_sync_at'])
        return connection
    except GoogleCalendarError as exc:
        error_text = str(exc)
        connection.last_sync_error = error_text
        connection.save(update_fields=['last_sync_error', 'updated_at'])
        faculty.current_status = faculty.manual_status
        if any(marker in error_text.casefold() for marker in ('401', 'authorization has expired', 'invalid_grant')):
            faculty.sync_enabled = False
            faculty.save(update_fields=['current_status', 'sync_enabled'])
            ConsultationRequest.objects.filter(
                faculty=faculty,
                google_calendar_id=connection.calendar_id,
            ).update(
                google_event_id=None,
                google_calendar_id=None,
                calendar_sync_status='not_configured',
            )
            connection.delete()
        else:
            faculty.save(update_fields=['current_status'])
        raise


def refresh_faculty_status(faculty, google_events=None):
    """Derive status from local, synced, and approved consultation records."""
    now = timezone.localtime(
        timezone.now(),
        ZoneInfo(getattr(settings, 'GOOGLE_CALENDAR_TIME_ZONE', settings.TIME_ZONE)),
    )
    active_status = None
    calendar_events = ScheduleEvent.objects.filter(
        faculty=faculty,
    ).filter(
        models.Q(date=now.date())
        | models.Q(start_month__isnull=False)
        | models.Q(date__isnull=True)
    ).filter(
        # Local events are always part of the system calendar. Synced Google
        # events count while their latest local copy is still in sync.
        models.Q(google_event_id__isnull=True)
        | models.Q(managed_by_facsync=True)
        | models.Q(sync_state='synced')
    )

    status_priority = {'busy': 1, 'virtual_only': 2, 'on_leave': 3}

    def consider_event(
        event_date,
        start_time,
        end_time,
        candidate,
        recurring_day=None,
        start_month=None,
        end_month=None,
    ):
        nonlocal active_status
        if event_date is None or start_month is not None:
            if end_month is None:
                return
            month_is_active = (
                start_month <= now.month <= end_month
                if start_month <= end_month
                else now.month >= start_month or now.month <= end_month
            )
            if not month_is_active:
                return
            if recurring_day and recurring_day != now.strftime('%A').casefold():
                return
            event_date = now.date()
        elif event_date != now.date():
            return
        if start_time is None:
            is_active = True
        else:
            start = datetime.combine(event_date, start_time)
            end = datetime.combine(event_date, end_time or start_time)
            if end <= start:
                end += timedelta(days=1)
            is_active = start <= now.replace(tzinfo=None) < end
        if is_active and (active_status is None or status_priority[candidate] > status_priority[active_status]):
            active_status = candidate

    for event in calendar_events:
        candidate = 'on_leave' if event.event_type == 'on-leave' else (
            'virtual_only' if event.event_type == 'virtual' else 'busy'
        )
        consider_event(
            event.date,
            event.start_time,
            event.end_time,
            candidate,
            event.day_of_week,
            event.start_month,
            event.end_month,
        )

    # Approved system consultations occupy the calendar even when their
    # Google event has not been synchronized yet.
    for consultation in ConsultationRequest.objects.filter(
        faculty=faculty,
        date=now.date(),
        status='approved',
    ):
        consider_event(consultation.date, consultation.start_time, consultation.end_time, 'busy')

    # During a sync, include the fresh Google response immediately as well as
    # the reconciled local records, so status does not wait for another read.
    for item in google_events or []:
        if item.get('status') == 'cancelled' or item.get('transparency') == 'transparent':
            continue
        values = _google_event_values(item)
        if values:
            candidate = 'on_leave' if values['event_type'] == 'on-leave' else (
                'virtual_only' if values['event_type'] == 'virtual' else 'busy'
            )
            consider_event(values['date'], values['start_time'], values['end_time'], candidate)

    next_status = faculty.manual_status if faculty.manual_status_override else (active_status or faculty.manual_status)
    if faculty.current_status != next_status:
        changed_at = timezone.now()
        faculty.current_status = next_status
        faculty.status_updated_at = changed_at
        faculty.save(update_fields=['current_status', 'status_updated_at'])
        StatusHistory.objects.create(
            history_id=secrets.token_hex(16),
            faculty=faculty,
            status=next_status,
            changed_at=changed_at,
        )
        notify_faculty_status_subscribers(faculty, next_status)
    return next_status


def _update_status_from_calendar(faculty, google_events=None):
    """Backward-compatible wrapper for calendar sync callers."""
    return refresh_faculty_status(faculty, google_events=google_events)


def disconnect_google_calendar(user):
    """Revoke Google access, disable sync, clear local links, and remove the connection."""
    connection = GoogleCalendarConnection.objects.filter(user=user).first()
    if not connection:
        return

    try:
        token = _access_token(connection)
        requests.post(
            'https://oauth2.googleapis.com/revoke',
            params={'token': token},
            timeout=20,
        )
    except (GoogleCalendarError, requests.RequestException):
        # Local disconnect must still work if Google is temporarily unavailable.
        pass

    faculty = FacultyProfile.objects.filter(user=user).first()
    if faculty:
        faculty.sync_enabled = False
        faculty.last_calendar_sync_at = None
        faculty.save(update_fields=['sync_enabled', 'last_calendar_sync_at'])
        ScheduleEvent.objects.filter(
            faculty=faculty,
            google_calendar_id=connection.calendar_id,
            google_event_id__isnull=False,
        ).delete()
        ConsultationRequest.objects.filter(
            faculty=faculty,
            google_calendar_id=connection.calendar_id,
            google_event_id__isnull=False,
        ).update(
            google_event_id=None,
            google_calendar_id=None,
            calendar_sync_status='not_configured',
            calendar_sync_error='',
            last_calendar_sync_at=None,
        )
    connection.delete()
