"""Duplicate detection for locally stored schedule events."""

from apps.faculty.models import ScheduleEvent


DUPLICATE_FIELDS = (
    'title', 'date', 'day_of_week', 'start_month', 'end_month',
    'recurrence_start_date', 'recurrence_end_date', 'start_time', 'end_time',
)


def schedule_event_duplicate(faculty, values, *, exclude_pk=None):
    """Return whether the same calendar placement or recurring range exists."""
    query = ScheduleEvent.objects.filter(faculty=faculty)
    if exclude_pk is not None:
        query = query.exclude(pk=exclude_pk)

    if values.get('date') is not None:
        return query.filter(
            **{field: values.get(field) for field in DUPLICATE_FIELDS},
        ).exists()

    recurring_day = values.get('day_of_week')
    if not recurring_day:
        return query.filter(
            **{field: values.get(field) for field in DUPLICATE_FIELDS},
        ).exists()

    candidates = query.filter(
        title=values.get('title'),
        date__isnull=True,
        day_of_week=recurring_day,
        start_time=values.get('start_time'),
        end_time=values.get('end_time'),
    )
    return any(_recurrence_ranges_overlap(values, candidate) for candidate in candidates)


def _month_set(start_month, end_month):
    """Return the inclusive months covered by a recurring range."""
    if start_month is None or end_month is None:
        return set()
    if start_month <= end_month:
        return set(range(start_month, end_month + 1))
    return set(range(start_month, 13)) | set(range(1, end_month + 1))


def _recurrence_ranges_overlap(values, existing):
    """Return whether two recurring events cover any of the same dates."""
    start = values.get('recurrence_start_date')
    end = values.get('recurrence_end_date')
    existing_start = existing.recurrence_start_date
    existing_end = existing.recurrence_end_date

    if start and end and existing_start and existing_end:
        return max(start, existing_start) <= min(end, existing_end)

    return bool(
        _month_set(values.get('start_month'), values.get('end_month'))
        & _month_set(existing.start_month, existing.end_month)
    )


def schedule_event_key(values):
    """Return a hashable identity for duplicate checks within one upload."""
    return tuple(values.get(field) for field in DUPLICATE_FIELDS)
