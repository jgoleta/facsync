"""Recipient and booking boundaries for department/office notices."""
from .models import OfficeClosure


def unit_closures(user):
    if user.department_id:
        return OfficeClosure.objects.filter(department_id=user.department_id, school_id=user.school_id)
    return OfficeClosure.objects.filter(department__isnull=True, college__iexact=user.college or '', school_id=user.school_id)


def faculty_closed(profile):
    return unit_closures(profile.user).filter(is_closed=True).exists()
