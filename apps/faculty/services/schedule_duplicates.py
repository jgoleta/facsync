"""Duplicate detection for locally stored schedule events."""

from apps.faculty.models import ScheduleEvent


DUPLICATE_FIELDS = (
    'title', 'date', 'day_of_week', 'start_month', 'end_month',
    'recurrence_start_date', 'recurrence_end_date', 'start_time', 'end_time',
)


def schedule_event_duplicate(faculty, values, *, exclude_pk=None):
    """Return whether the same calendar placement already exists."""
    query = ScheduleEvent.objects.filter(
        faculty=faculty,
        **{field: values.get(field) for field in DUPLICATE_FIELDS},
    )
    if exclude_pk is not None:
        query = query.exclude(pk=exclude_pk)
    return query.exists()


def schedule_event_key(values):
    """Return a hashable identity for duplicate checks within one upload."""
    return tuple(values.get(field) for field in DUPLICATE_FIELDS)
