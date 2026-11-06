"""Supported profile levels and authoritative grade/year choices."""
from django.core.exceptions import ValidationError

LEVEL_CHOICES = [('elementary', 'Elementary'), ('jhs', 'Junior High School'),
                 ('shs', 'Senior High School'), ('college', 'College')]
LEVELS = dict(LEVEL_CHOICES)
YEAR_CHOICES = {
    'elementary': [(str(n), f'Grade {n}') for n in range(1, 7)],
    'jhs': [(str(n), f'Grade {n}') for n in range(7, 11)],
    'shs': [(str(n), f'Grade {n}') for n in range(11, 13)],
    'college': [(str(n), f'Year {n}') for n in range(1, 7)],
}


def default_levels():
    return ['college']


def validate_announcement_levels(value):
    if (not isinstance(value, list) or any(not isinstance(item, str) or item not in LEVELS for item in value)
            or len(set(value)) != len(value)):
        raise ValidationError('Choose valid educational levels without duplicates.')


def validate_school_levels(value):
    validate_announcement_levels(value)
    if not value:
        raise ValidationError('Select at least one educational level.')


def ordered_levels(value):
    return [key for key, _ in LEVEL_CHOICES if key in value]
