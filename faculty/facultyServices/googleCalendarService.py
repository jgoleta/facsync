import secrets
from datetime import date, datetime, time, timedelta
from hmac import compare_digest
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

import requests
from django.conf import settings
from django.urls import reverse
from django.utils import timezone

from faculty.models import FacultyProfile, GoogleCalendarConnection, ScheduleEvent


GOOGLE_AUTH_URL = 'https://accounts.google.com/o/oauth2/v2/auth'
GOOGLE_TOKEN_URL = 'https://oauth2.googleapis.com/token'
GOOGLE_USERINFO_URL = 'https://www.googleapis.com/oauth2/v3/userinfo'
GOOGLE_CALENDAR_URL = 'https://www.googleapis.com/calendar/v3'
GOOGLE_CALENDAR_SCOPE = 'https://www.googleapis.com/auth/calendar.events'


class GoogleCalendarError(Exception):
    pass


def _client_credentials():
    client_id = getattr(settings, 'GOOGLE_CLIENT_ID', '')
    client_secret = getattr(settings, 'GOOGLE_CLIENT_SECRET', '')
    if not client_id or not client_secret:
        raise GoogleCalendarError('Google Calendar credentials are not configured.')
    return client_id, client_secret


def callback_url(request):
    return request.build_absolute_uri(reverse('faculty:calendar_callback'))


def start_oauth(request):
    client_id, _ = _client_credentials()
    state = secrets.token_urlsafe(32)
    request.session['google_calendar_oauth_state'] = state
    params = {
        'client_id': client_id,
        'redirect_uri': callback_url(request),
        'response_type': 'code',
        'scope': GOOGLE_CALENDAR_SCOPE,
        'access_type': 'offline',
        'prompt': 'consent',
        'include_granted_scopes': 'true',
        'state': state,
    }
    return f'{GOOGLE_AUTH_URL}?{urlencode(params)}'


def _token_request(data):
    try:
        response = requests.post(GOOGLE_TOKEN_URL, data=data, timeout=20)
    except requests.RequestException as exc:
        raise GoogleCalendarError('Unable to contact Google OAuth.') from exc
    if not response.ok:
        raise GoogleCalendarError('Google OAuth token exchange failed.')
    return response.json()


def finish_oauth(request, code, state):
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
    if not force_refresh and connection.token_expires_at:
        if connection.token_expires_at > timezone.now() + timedelta(seconds=60):
            return connection.access_token
    if not force_refresh and connection.access_token and not connection.refresh_token:
        return connection.access_token
    return _refresh_access_token(connection)


def google_request(connection, method, path, **kwargs):
    url = f'{GOOGLE_CALENDAR_URL}{path}'
    for attempt in range(2):
        headers = kwargs.pop('headers', {}).copy()
        headers['Authorization'] = f'Bearer {_access_token(connection, force_refresh=attempt == 1)}'
        try:
            response = requests.request(method, url, headers=headers, timeout=20, **kwargs)
        except requests.RequestException as exc:
            raise GoogleCalendarError('Unable to contact Google Calendar.') from exc
        if response.status_code != 401 or attempt == 1:
            if not response.ok:
                raise GoogleCalendarError(
                    f'Google Calendar request failed ({response.status_code}).'
                )
            return response
    raise GoogleCalendarError('Google Calendar authorization failed.')


def list_google_events(connection):
    events = []
    page_token = None
    while True:
        params = {
            'singleEvents': 'true',
            'showDeleted': 'false',
            'maxResults': 2500,
            'orderBy': 'startTime',
            'timeZone': getattr(settings, 'GOOGLE_CALENDAR_TIME_ZONE', settings.TIME_ZONE),
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
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
    calendar_timezone = ZoneInfo(
        getattr(settings, 'GOOGLE_CALENDAR_TIME_ZONE', settings.TIME_ZONE)
    )
    return timezone.localtime(parsed, calendar_timezone)


def _google_event_values(item, existing=None):
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
    payload = {
        'summary': event.title,
        'description': event.description or '',
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
    response = google_request(
        connection,
        'POST',
        f'/calendars/{connection.calendar_id}/events',
        json=google_event_payload(event),
    )
    return response.json()


def update_google_event(connection, event):
    response = google_request(
        connection,
        'PUT',
        f'/calendars/{connection.calendar_id}/events/{event.google_event_id}',
        json=google_event_payload(event),
    )
    return response.json()


def delete_google_event(connection, event):
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
    connection = GoogleCalendarConnection.objects.get(user=user)
    faculty = FacultyProfile.objects.get(user=user)
    google_events = list_google_events(connection)
    seen_ids = set()

    for item in google_events:
        if item.get('status') == 'cancelled' or not item.get('id'):
            continue
        values = _google_event_values(item)
        if values is None:
            continue
        event_id = item['id']
        seen_ids.add(event_id)
        event = ScheduleEvent.objects.filter(
            faculty=faculty,
            google_calendar_id=connection.calendar_id,
            google_event_id=event_id,
        ).first()
        if event:
            values['google_event_id'] = event_id
            values['google_calendar_id'] = connection.calendar_id
            for field, value in values.items():
                setattr(event, field, value)
            event.save(update_fields=list(values.keys()) + ['updated_at'])
        else:
            ScheduleEvent.objects.create(
                faculty=faculty,
                google_event_id=event_id,
                google_calendar_id=connection.calendar_id,
                **values,
            )

    stale_events = ScheduleEvent.objects.filter(
        faculty=faculty,
        google_calendar_id=connection.calendar_id,
        google_event_id__isnull=False,
    )
    if seen_ids:
        stale_events.exclude(google_event_id__in=seen_ids).delete()
    else:
        stale_events.delete()

    # Local records created before Google Calendar was connected are linked now.
    local_only_events = ScheduleEvent.objects.filter(
        faculty=faculty,
        google_event_id__isnull=True,
    )
    for event in local_only_events:
        google_event = create_google_event(connection, event)
        event.google_event_id = google_event.get('id')
        event.google_calendar_id = connection.calendar_id
        event.save(update_fields=['google_event_id', 'google_calendar_id', 'updated_at'])

    now = timezone.now()
    connection.last_synced_at = now
    connection.save(update_fields=['last_synced_at', 'updated_at'])
    faculty.last_calendar_sync_at = now
    faculty.save(update_fields=['last_calendar_sync_at'])
    return connection


def disconnect_google_calendar(user):
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
        ScheduleEvent.objects.filter(
            faculty=faculty,
            google_calendar_id=connection.calendar_id,
            google_event_id__isnull=False,
        ).delete()
    connection.delete()
