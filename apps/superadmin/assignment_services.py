"""Validated assignments shared by School Admin forms and first-login activation."""
from django.core.exceptions import ValidationError

from apps.core.models import Department
from apps.faculty.models import ConsultationRequest, ScheduleEvent, StatusHistory, WalkInQueue


def lock_departments(departments, school):
    ids = {item.pk for item in departments}
    locked = list(Department.objects.select_for_update().filter(pk__in=ids, school=school, is_active=True).order_by('pk'))
    if not ids or len(locked) != len(ids):
        raise ValidationError('A selected department is no longer active or available. Please refresh and try again.')
    return locked


def faculty_has_activity(user):
    return (ConsultationRequest.objects.filter(faculty__user=user).exists()
            or WalkInQueue.objects.filter(faculty__user=user).exists()
            or StatusHistory.objects.filter(faculty__user=user).exists()
            or ScheduleEvent.objects.filter(faculty__user=user).exists())
