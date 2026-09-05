"""Shared calendar event serialization for faculty and student calendars."""


def get_schedule_status_label(event):
    if event.schedule_status:
        return event.schedule_status
    return dict(event.EVENT_TYPES).get(event.event_type, event.event_type)


def serialize_schedule_event(event, include_sync_metadata=False, human_status=False):
    """Serialize a schedule event using the common calendar response shape."""
    payload = {
        'id': event.pk,
        'title': event.title,
        'description': event.description,
        'location': event.location,
        'status': get_schedule_status_label(event) if human_status else (event.schedule_status or event.event_type),
        'event_type': event.event_type,
        'date': event.date.isoformat() if event.date else None,
        'is_recurring': event.date is None,
        'day_of_week': '' if event.day_of_week == 'none' else event.day_of_week,
        'start_month': event.start_month,
        'end_month': event.end_month,
        'recurrence_start_date': event.recurrence_start_date.isoformat() if event.recurrence_start_date else None,
        'recurrence_end_date': event.recurrence_end_date.isoformat() if event.recurrence_end_date else None,
        'start_time': event.start_time.isoformat() if event.start_time else None,
        'end_time': event.end_time.isoformat() if event.end_time else None,
    }
    if include_sync_metadata:
        payload.update({
            'google_event_id': event.google_event_id,
            'sync_state': event.sync_state,
            'sync_error': event.sync_error,
        })
    return payload


def serialize_consultation_event(consultation, viewer='student'):
    """Serialize an approved consultation for the requested calendar viewer."""
    if viewer == 'faculty':
        participant_name = consultation.user.get_full_name() or consultation.user.username
    else:
        participant_name = consultation.faculty.user.get_full_name() or consultation.faculty.user.username

    payload = {
        'id': f'consultation:{consultation.request_id}',
        'request_id': consultation.request_id,
        'title': f'Consultation with {participant_name}',
        'description': consultation.student_message or 'Approved student consultation.',
        'location': consultation.faculty.office_location,
        'status': 'Consultation',
        'event_type': 'busy',
        'date': consultation.date.isoformat(),
        'is_recurring': False,
        'is_consultation': True,
        'day_of_week': '',
        'start_month': None,
        'end_month': None,
        'start_time': consultation.start_time.isoformat() if consultation.start_time else None,
        'end_time': consultation.end_time.isoformat() if consultation.end_time else None,
    }
    if viewer == 'faculty':
        payload['google_event_id'] = consultation.google_event_id
    return payload
