"""Aggregate-only reporting; individual feedback is returned only to its author."""
from django.db.models import Avg, Count

MINIMUM_RATINGS = 5


def satisfaction_summary(consultations):
    result = consultations.filter(status='completed', satisfaction_rating__isnull=False).aggregate(
        response_count=Count('pk'), average=Avg('satisfaction_rating'))
    enough = result['response_count'] >= MINIMUM_RATINGS
    return {
        'response_count': result['response_count'],
        'minimum_responses': MINIMUM_RATINGS,
        'has_enough_data': enough,
        'average': round(result['average'], 1) if enough else None,
    }
