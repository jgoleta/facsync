"""Plain-text presentation for the preset helpers (never generated HTML)."""
from datetime import date


def date_label(value):
    if isinstance(value, str):
        value = date.fromisoformat(value)
    return f'{value:%B} {value.day}, {value.year}'


def date_range(start, end):
    return f'{date_label(start)} to {date_label(end)}'


def quantity(count, singular, plural=None):
    return f'{count} {singular if count == 1 else plural or singular + "s"}'


def duration(minutes):
    hours, minutes = divmod(int(minutes), 60)
    parts = []
    if hours:
        parts.append(quantity(hours, 'hour'))
    if minutes or not parts:
        parts.append(quantity(minutes, 'minute'))
    return ' '.join(parts)


def hour_range(hour):
    clock = hour % 12 or 12
    suffix = 'AM' if hour < 12 else 'PM'
    return f'{clock} {suffix}–{clock}:59 {suffix}'


def answer(intro, lines, note, source_url, source_label, *, empty='', paragraphs=False):
    if not lines and empty:
        intro, lines, paragraphs = '', [empty], True
    return {'period': intro, 'lines': lines, 'note': note, 'source_url': source_url,
            'source_label': source_label, 'presentation': 'paragraphs' if paragraphs else 'list'}
